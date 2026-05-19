"""Milvus 与本地检索回退封装。

本模块是企业 RAG 检索链路中的向量存储与检索入口，对应 RAG 流程中的
"Hybrid Retrieval"阶段（dense 主路径 + sparse 补充路径 + 本地词法兜底路径）。

上下游关联：
- 上游写入端：KnowledgeIngestionService._index_documents（backend/app/services/knowledge_ingestion_service.py）
  在文档接入流程最后一步调用 index_documents()，把解析切分后的 Document 列表送入本模块；
- 上游权限端：AccessPolicyResolver（backend/app/services/access_policy_service.py）
  把当前用户上下文解析为 AccessPolicy 对象，供 search() 方法的 access_policy 参数使用；
- 下游消费端：retrieval_pipeline（后续 commit 将在 backend/app/services/rag/retrieval_pipeline.py 实现）
  调用 search() 获取候选 chunk，再经 RRF 融合与 rerank 后生成最终引用。

安全约束：
dense 主路径、sparse 补充路径、本地词法兜底路径三套链路必须复用同一套 ACL 过滤。
若 Milvus 服务异常导致回退到本地词法检索，而本地路径未执行等价 ACL，则会造成越权泄露。
因此 search() 统一接收 AccessPolicy，dense 与本地回退都必须经过同一套过滤逻辑。
"""

from __future__ import annotations

import json
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from langchain_core.documents import Document
from langchain_milvus import Milvus

from app.core.config import get_settings
from app.core.llm import get_embeddings_model
from app.models.knowledge import DocumentStatus, VisibilityScope
from app.models.knowledge_retrieval import AccessPolicy

TOKEN_PATTERN = re.compile(r"[一-鿿A-Za-z0-9]+")


class KnowledgeVectorStore:
    """优先使用 Milvus dense 检索，失败时回退到本地词法检索。

    职责定位：
    索引侧同时维护内存 records、本地文件索引、Milvus 向量索引三份数据；
    检索侧先尝试 Milvus dense search，异常时回退到本地 _lexical_search；
    过滤侧 search 方法统一接收 AccessPolicy，保证 dense 和本地回退执行同一套过滤。
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._records: list[Document] = []
        self._milvus: Milvus | None = None

    def index_documents(self, documents: list[Document]) -> None:
        """建立文档索引。

        本函数是知识接入流程（ingestion pipeline）的最后一步，被
        KnowledgeIngestionService._index_documents 直接调用。
        入参 documents 是已经切分好的 Document 列表，每个 Document 的 metadata
        中应包含 doc_id、chunk_id、department、visibility_scope、status、is_latest
        等字段，供后续检索侧 ACL 过滤使用。

        执行动作：
        1. 把 documents 保存到内存 self._records；
        2. 调用 _persist_local_index 序列化到本地 JSON 文件，作为 Milvus 不可用时
           的兜底数据源；
        3. 调用 _try_build_milvus_index 把 documents 写入 Milvus 向量索引。
           Milvus 写入失败时不抛异常，self._milvus 置为 None，后续检索自动回退本地。
        """
        self._records = documents
        self._persist_local_index(documents)
        self._try_build_milvus_index(documents)

    def search(
        self,
        query: str,
        *,
        keywords: list[str] | None = None,
        access_policy: AccessPolicy | None = None,
        history_lookup: bool = False,
        bias_mode: str = "balanced",
        top_k: int | None = None,
    ) -> list[dict[str, Any]]:
        """执行检索，返回带 ACL 过滤的候选 chunk 列表。

        本函数是企业 RAG 检索链路的核心入口，对应 RAG 流程中 Hybrid Retrieval 阶段。
        下游被 retrieval_pipeline 调用，返回值经 RRF 融合与 rerank 后用于生成回答。

        参数说明：
        - query: 用户查询字符串，由 QueryRewriteService 改写后传入；
        - keywords: QueryRewriteService 提取的关键词列表，作为 sparse 检索补充输入。
          若传入 None 或空列表，则跳过 sparse 路径；
        - access_policy: ACL 统一过滤对象，由 AccessPolicyResolver 根据当前用户角色、
          部门、项目权限解析生成。若传入 None，则使用默认过滤规则；
        - history_lookup: 是否开启历史版本查询模式。为 True 时放宽 is_latest 限制，
          允许命中 deprecated 或过期版本文档，用于审计或追溯场景；
        - bias_mode: 检索偏向总开关，取值 balanced / semantic_bias / keyword_bias。
          semantic_bias 时扩大 dense 候选、缩减 sparse 候选；keyword_bias 时反之；
        - top_k: 返回候选数量上限，默认读取 config.knowledge_top_k。

        执行路径：
        1. dense 主路径：若 self._milvus 不为 None，调用 Milvus.max_marginal_relevance_search
           做向量检索，expr 参数由 _build_milvus_filter 根据 access_policy 生成；
        2. sparse 补充路径：无论 dense 是否成功，都调用 _sparse_search 基于 keywords
           获取文本匹配候选，弥补 dense embedding 对罕见词的召回不足；
        3. 若 Milvus 异常或不可用，自动回退到 _lexical_search 本地词法检索；
        4. 本地回退路径同样接收 access_policy 与 history_lookup，通过 _document_passes_acl
           执行与 dense 路径等价的 ACL 过滤。

        返回值：
        list[dict]，每个 dict 包含 doc_id、chunk_id、content、source_file、
        section_path、page_num、department、doc_type、score、snippet、token_count 等字段，
        供下游 citation_builder 打包为引用来源。
        """
        top_k = top_k or self._settings.knowledge_top_k

        # 根据 bias_mode 调整 dense / sparse 的候选规模比例
        dense_top_k = top_k
        sparse_top_k = top_k
        if bias_mode == "semantic_bias":
            dense_top_k = int(top_k * 1.5)
            sparse_top_k = max(1, int(top_k * 0.5))
        elif bias_mode == "keyword_bias":
            dense_top_k = max(1, int(top_k * 0.5))
            sparse_top_k = int(top_k * 1.5)

        dense_results: list[dict[str, Any]] = []
        if self._milvus is not None:
            try:
                expression = self._build_milvus_filter(access_policy, history_lookup=history_lookup)
                docs = self._milvus.max_marginal_relevance_search(query, k=dense_top_k, expr=expression)
                dense_results = [self._to_search_result(doc, self._lexical_score(query, doc.page_content)) for doc in docs]
            except Exception:
                pass

        # sparse 补充路径：基于 keywords 做文本匹配，不替换 dense 结果
        sparse_results: list[dict[str, Any]] = []
        if keywords:
            sparse_results = self._sparse_search(
                query, keywords,
                access_policy=access_policy,
                history_lookup=history_lookup,
                top_k=sparse_top_k,
            )

        # 若 dense 无结果且 sparse 无结果，回退到本地词法检索
        if not dense_results and not sparse_results:
            return self._lexical_search(
                query, access_policy=access_policy, history_lookup=history_lookup, top_k=top_k
            )

        # 简单合并 dense + sparse，按 chunk_id 去重（RRF 阶段会做更精细的融合）
        seen_ids: set[str] = set()
        merged: list[dict[str, Any]] = []
        for item in dense_results + sparse_results:
            cid = item.get("chunk_id", "")
            if cid and cid in seen_ids:
                continue
            if cid:
                seen_ids.add(cid)
            merged.append(item)
        return merged

    def _build_milvus_filter(self, access_policy: AccessPolicy | None, *, history_lookup: bool) -> str | None:
        """构建 Milvus 过滤表达式，供 dense 主路径的 expr 参数使用。

        本函数是 dense 路径的 ACL 落地点。Milvus 通过 expr 字符串在服务端过滤候选，
        因此所有权限条件必须被序列化为 Milvus 支持的布尔表达式。

        构建规则：
        1. 若传入 access_policy 且其 milvus_filter 非空，优先透传该表达式。
           该表达式由 AccessPolicyResolver 统一生成，已包含 status、is_latest、
           visibility_scope、department、project_ids、owner_user_id 等完整条件；
        2. 若未传入 policy，则使用本地默认兜底规则：
           status == "active" and is_latest == true；
        3. history_lookup=True 时，把 is_latest == true 替换为
           is_latest == true or is_latest == false，从而允许命中历史版本，
           但保留其他 ACL 条件不变。

        返回值：
        str 类型的 Milvus 过滤表达式，直接传入 Milvus.max_marginal_relevance_search 的 expr 参数。
        """
        if access_policy is not None and access_policy.milvus_filter:
            base = access_policy.milvus_filter
        else:
            parts = [f'status == "{DocumentStatus.ACTIVE.value}"', "is_latest == true"]
            base = " and ".join(parts)

        if history_lookup:
            # history_lookup 模式下把 is_latest 限制放宽为既允许 true 也允许 false，
            # 从而命中历史版本和已作废文档，但保留其他 ACL 条件不变。
            base = base.replace("is_latest == true", "is_latest == true or is_latest == false")

        return base

    def _try_build_milvus_index(self, documents: list[Document]) -> None:
        """尝试构建 Milvus 向量索引。

        本函数在 index_documents 内部调用，负责把 Document 列表写入 Milvus。
        使用 langchain_milvus.Milvus 封装类，embedding_function 来自 get_embeddings_model
        （backend/app/core/llm.py）。

        配置参数：
        - collection_name: 取自 config.milvus_collection_name；
        - connection_args: host/port/secure 取自 config；
        - index_params: COSINE 相似度 + HNSW 图索引（M=16, efConstruction=200）；
        - search_params: ef=64；
        - drop_old=False: 不删除已有集合，支持增量写入；
        - auto_id=True: 自动生成主键；
        - text_field="content": 存储原始文本的字段名；
        - metadata_field="metadata": 存储附加 metadata 的字段名；
        - partition_key_field="department": 按部门做分区键，提升多租户场景下的检索效率；
        - num_partitions=4: 分区数量。

        异常处理：
        Milvus 连接或写入失败时不抛异常，self._milvus 置为 None，
        保证 ingestion 流程不因向量层故障而中断，后续检索自动回退本地词法路径。
        """
        embeddings = get_embeddings_model()
        if embeddings is None or not documents:
            return

        try:
            self._milvus = Milvus(
                embedding_function=embeddings,
                collection_name=self._settings.milvus_collection_name,
                connection_args={
                    "host": self._settings.milvus_host,
                    "port": self._settings.milvus_port,
                    "secure": self._settings.milvus_secure,
                },
                index_params={
                    "metric_type": "COSINE",
                    "index_type": "HNSW",
                    "params": {"M": 16, "efConstruction": 200},
                },
                search_params={
                    "metric_type": "COSINE",
                    "params": {"ef": 64},
                },
                drop_old=False,
                auto_id=True,
                text_field="content",
                metadata_field="metadata",
                partition_key_field="department",
                num_partitions=4,
            )
            self._milvus.add_documents(documents)
        except Exception:
            self._milvus = None

    def _lexical_search(
        self,
        query: str,
        *,
        access_policy: AccessPolicy | None = None,
        history_lookup: bool = False,
        top_k: int,
    ) -> list[dict[str, Any]]:
        """本地词法回退检索，仅在 Milvus 不可用时执行。

        本函数是 dense 主路径的兜底备份，对应 RAG 流程中的 fallback retrieval。
        安全上必须与 dense 路径复用完全一致的 ACL 逻辑，否则 Milvus 异常时
        本地回退会变成越权泄露通道。

        执行流程：
        1. 遍历 self._records 内存中的全部 chunk；
        2. 对每个 chunk 调用 _document_passes_acl 进行统一 ACL 过滤，
           未通过过滤的文档不进入候选集，不参与后续排序；
        3. 对通过过滤的文档计算 _lexical_score（基于 token 重叠率）；
        4. 使用 MMR（Maximal Marginal Relevance）在候选中选择 top_k 条结果，
           lambda_weight=0.65 控制相关性与多样性的权衡。

        返回值：
        与 search() 同格式的 list[dict]，供下游统一消费。
        """
        candidates = []
        for doc in self._records:
            if not self._document_passes_acl(doc.metadata, access_policy, history_lookup=history_lookup):
                continue
            score = self._lexical_score(query, doc.page_content)
            if score > 0:
                candidates.append((doc, score, self._tokenize(doc.page_content)))

        selected: list[tuple[Document, float, set[str]]] = []
        lambda_weight = 0.65
        while candidates and len(selected) < top_k:
            def mmr_value(candidate: tuple[Document, float, set[str]]) -> float:
                _, relevance, candidate_tokens = candidate
                diversity_penalty = 0.0
                if selected:
                    diversity_penalty = max(self._jaccard(candidate_tokens, item[2]) for item in selected)
                return lambda_weight * relevance - (1 - lambda_weight) * diversity_penalty

            best = max(candidates, key=mmr_value)
            selected.append(best)
            candidates.remove(best)

        return [self._to_search_result(doc, score) for doc, score, _ in selected]

    def _sparse_search(
        self,
        query: str,
        keywords: list[str],
        *,
        access_policy: AccessPolicy | None = None,
        history_lookup: bool = False,
        top_k: int,
    ) -> list[dict[str, Any]]:
        """本地稀疏检索（BM25 近似），基于 keywords 做词频评分。

        本函数是 hybrid retrieval 中的 sparse 补充路径，对应 RAG 流程中
        dense 向量检索之外的文本匹配通道。当用户查询包含明确的关键词时，
        sparse 路径能弥补 dense embedding 对罕见词或专有名词的召回不足。

        与 _lexical_search 的区别：
        - _lexical_search 使用完整 query 做 token 重叠，作为 Milvus 不可用时
          的纯兜底路径；
        - _sparse_search 使用 QueryRewriteService 提取的 keywords 做命中评分，
          作为 hybrid retrieval 中与 dense 结果并列的一路候选源。

        评分规则：
        对每个通过 ACL 的 chunk，统计 keywords 在 content 中的命中比例：
        score = 命中关键词数 / max(len(keywords), 1)
        该得分范围 (0, 1]，1 表示所有关键词都命中。

        参数：
        - query: 用户查询字符串（保留参数位置统一，当前实现主要用 keywords）；
        - keywords: QueryRewriteService 提取的关键词列表，是 sparse 检索的核心输入；
        - access_policy: ACL 统一过滤对象；
        - history_lookup: 是否开启历史版本查询；
        - top_k: 返回候选数量上限。

        返回值：
        与 _lexical_search 同格式的 list[dict]，供下游 RRF 融合统一消费。
        """
        if not keywords:
            return []

        keyword_set = {k.lower() for k in keywords}
        candidates = []
        for doc in self._records:
            if not self._document_passes_acl(doc.metadata, access_policy, history_lookup=history_lookup):
                continue
            content_lower = doc.page_content.lower()
            hits = sum(1 for kw in keyword_set if kw in content_lower)
            score = hits / max(len(keyword_set), 1)
            if score > 0:
                candidates.append((doc, score))

        # 按得分降序取 top_k，暂不做 MMR（由 RRF 阶段统一去重）
        candidates.sort(key=lambda x: x[1], reverse=True)
        selected = candidates[:top_k]
        return [self._to_search_result(doc, score) for doc, score in selected]

    def _document_passes_acl(
        self,
        metadata: dict[str, Any],
        access_policy: AccessPolicy | None,
        *,
        history_lookup: bool = False,
    ) -> bool:
        """判断单条文档是否通过 ACL 过滤。

        本函数是本地回退路径的核心安全检查点，必须与 _build_milvus_filter 生成的
        Milvus expr 语义完全一致。任何不一致都会导致同一批文档在 Milvus 可用与不可用
        时呈现不同可见性，形成权限窗口漏洞。

        判断顺序：
        1. 状态过滤：默认只允许 ACTIVE 和 SYNC_PENDING 文档进入候选集。
           DEPRECATED、INDEX_FAILED、PARSE_FAILED 等状态默认被排除；
           history_lookup=True 时放宽此限制，允许命中 deprecated 文档；
        2. 版本过滤：默认只保留 is_latest=True 的最新版本文档；
           history_lookup=True 时放宽，允许命中历史版本；
        3. visibility_scope 分级过滤（仅当 access_policy 非 None 时执行）：
           - PUBLIC: 所有登录用户可见，直接返回 True；
           - DEPARTMENT: 检查 metadata["department"] 是否在 policy.allowed_departments；
           - PROJECT: 检查 metadata["project_ids"] 与 policy.allowed_project_ids 是否有交集。
             若用户模型未启用 project_ids（has_project_ids_support 为 False），
             则 project scope 在 AccessPolicyResolver 阶段已被排除，不会进入此分支；
           - PRIVATE: 分两条通道：
             a) admin 通道：metadata["doc_id"] 在 policy.can_read_private_doc_ids 中；
             b) 普通用户通道：metadata["owner_user_id"] 等于 policy.user_id。

        返回值：
        True 表示文档可见，可进入候选集参与排序；
        False 表示文档被过滤，不能参与 merge/rerank，也不能出现在最终引用中。
        """
        status = metadata.get("status", DocumentStatus.ACTIVE.value)
        if status not in {DocumentStatus.ACTIVE.value, DocumentStatus.SYNC_PENDING.value}:
            if not history_lookup:
                return False

        if not history_lookup and not metadata.get("is_latest", True):
            return False

        if access_policy is None:
            return True

        scope = metadata.get("visibility_scope", VisibilityScope.PUBLIC.value)
        if scope == VisibilityScope.PUBLIC.value:
            return True
        if scope == VisibilityScope.DEPARTMENT.value:
            return metadata.get("department") in access_policy.allowed_departments
        if scope == VisibilityScope.PROJECT.value:
            doc_projects = set(metadata.get("project_ids", []))
            return bool(doc_projects & set(access_policy.allowed_project_ids))
        if scope == VisibilityScope.PRIVATE.value:
            if metadata.get("doc_id") in access_policy.can_read_private_doc_ids:
                return True
            return metadata.get("owner_user_id") == access_policy.user_id
        return True

    def _to_search_result(self, doc: Document, score: float) -> dict[str, Any]:
        """把 Document 转换为统一检索结果格式。

        本函数是检索侧与下游消费端的格式契约点。search() 与 _lexical_search()
        的返回值都经过此函数标准化，确保 dense 路径与本地回退路径的输出字段一致。

        下游消费方：
        - retrieval_pipeline: 读取 score、content 做 RRF 融合与 rerank；
        - citation_builder: 读取 doc_id、chunk_id、source_file、section_path、
          page_num 生成前端引用卡片；
        - generate_node: 读取 content、snippet 作为上下文拼入 prompt。

        输出字段：
        - doc_id: 文档唯一标识；
        - chunk_id: 片段唯一标识；
        - content: 完整 chunk 文本；
        - source_file: 原始文件名；
        - section_path: 标题路径，无标题时回退为空字符串；
        - page_num: 页码/片段序号；
        - department: 所属部门；
        - doc_type: 文档类型；
        - score: 检索得分（dense 或 lexical）；
        - snippet: 前 180 字摘要；
        - token_count: chunk 的 token 数，由 ingestion 阶段计算并写入 metadata。
        """
        return {
            "doc_id": str(doc.metadata.get("doc_id", "")),
            "chunk_id": str(doc.metadata.get("chunk_id", "")),
            "content": doc.page_content,
            "source_file": str(doc.metadata.get("source_file", "")),
            "section_path": str(doc.metadata.get("section_path", "")),
            "page_num": int(doc.metadata.get("page_num", 1)),
            "department": str(doc.metadata.get("department", "")),
            "doc_type": str(doc.metadata.get("doc_type", "")),
            "score": round(score, 4),
            "snippet": doc.page_content[:180],
            "token_count": int(doc.metadata.get("token_count", 0)),
        }

    def _lexical_score(self, query: str, content: str) -> float:
        """计算查询与内容的词法重叠得分。

        得分公式：overlap / sqrt(len(query_tokens) * len(content_tokens))
        其中 overlap 是 query 与 content 的共有 token 数。
        该得分范围 (0, 1]，0 表示无重叠，1 表示完全包含。
        """
        query_tokens = self._tokenize(query)
        content_tokens = self._tokenize(content)
        overlap = query_tokens.intersection(content_tokens)
        if not overlap:
            return 0.0
        return len(overlap) / math.sqrt(max(len(query_tokens), 1) * max(len(content_tokens), 1))

    def _persist_local_index(self, documents: list[Document]) -> None:
        """把 Document 列表序列化为本地 JSON 索引文件。

        文件路径由 config.knowledge_index_dir / "local_index.json" 决定。
        该文件作为 Milvus 完全不可用时的最后兜底数据源，在 _lexical_search 中
        通过 self._records 内存数据间接使用（index_documents 时同时写入内存与文件）。
        """
        payload = [{"page_content": document.page_content, "metadata": document.metadata} for document in documents]
        index_path = Path(self._settings.knowledge_index_dir) / "local_index.json"
        index_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _tokenize(self, text: str) -> set[str]:
        """基于正则的轻量分词，提取中文汉字、英文字母与数字序列。

        分词规则：
        - 连续中文字符按单字切分，保证中文查询的 token 级别匹配；
        - 连续英文字母与数字按整词切分，保留英文术语和编号完整性。

        返回值：
        token 集合，供 _lexical_score、_lexical_search、_sparse_search 使用。
        """
        tokens: list[str] = []
        for match in TOKEN_PATTERN.finditer(text):
            token = match.group()
            if any("一" <= c <= "鿿" for c in token):
                tokens.extend(token)
            else:
                tokens.append(token.lower())
        return set(tokens)

    @staticmethod
    def _jaccard(left: set[str], right: set[str]) -> float:
        """计算两个 token 集合的 Jaccard 相似度，用于 MMR 多样性惩罚。"""
        union = left.union(right)
        if not union:
            return 0.0
        return len(left.intersection(right)) / len(union)


@lru_cache
def get_knowledge_vectorstore() -> KnowledgeVectorStore:
    """返回全局单例 KnowledgeVectorStore 实例。

    本函数被 retrieval_pipeline 和 KnowledgeIngestionService._index_documents 调用，
    保证同一进程内索引与检索共用同一份内存 records 与 Milvus 连接。
    """
    return KnowledgeVectorStore()
