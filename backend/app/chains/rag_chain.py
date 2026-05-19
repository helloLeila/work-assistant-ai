"""RAG 链与检索器。

本模块是企业 RAG 检索链路的编排入口，对应 RAG 流程中的
"Rewrite → ACL → Hybrid Retrieval → RRF → Rerank → Grounded Answer" 阶段。

上下游关联：
- 上游调用方：knowledge_rag_node（backend/app/nodes/knowledge_rag_node.py）
  在 LangGraph 工作流中调用 run_rag_chain 获取检索结果；
- 上游依赖服务：
  - QueryRewriteService（backend/app/services/query_rewrite_service.py）：查询改写；
  - AccessPolicyResolver（backend/app/services/access_policy_service.py）：ACL 解析；
  - KnowledgeVectorStore（backend/app/vectorstore/milvus_client.py）：hybrid retrieval；
- 下游消费方：generate_node（backend/app/nodes/generate_node.py）使用检索到的 chunk
  构建带引用的回答；grader_node（backend/app/nodes/grader_node.py）对检索结果做相关性评分。

兼容说明：
run_rag_chain 保留旧接口签名与返回格式，作为 knowledge_rag_node 的兼容层；
新链路核心逻辑封装在 run_retrieval_pipeline 中，返回 KnowledgeAnswerPayload，
供后续 API 路由和节点直接消费。
"""

from __future__ import annotations

from typing import Any

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.retrievers import BaseRetriever
from langchain_core.runnables import RunnablePassthrough
from pydantic import PrivateAttr

from app.core.llm import get_chat_model
from app.core.security import CurrentUser
from app.models.knowledge_retrieval import (
    CitationItem,
    KnowledgeAnswerPayload,
    QueryRewriteResult,
    RetrievalDebugTrace,
)
from app.services.access_policy_service import resolve_access_policy
from app.services.knowledge_service import get_knowledge_service
from app.services.query_rewrite_service import QueryRewriteService, is_hyde_eligible
from app.vectorstore.milvus_client import KnowledgeVectorStore


class KnowledgeRetriever(BaseRetriever):
    """封装知识库服务，供 LCEL 使用。

    保留作为兼容层，后续 Commit 46-50 节点整合阶段将评估是否完全迁移到
    run_retrieval_pipeline。当前仍被 run_rag_chain 内部部分路径使用。
    """

    department: str | None = None
    doc_type: str | None = None
    _service = PrivateAttr()

    def __init__(self, *, department: str | None = None, doc_type: str | None = None) -> None:
        super().__init__(department=department, doc_type=doc_type)
        self._service = get_knowledge_service()

    def _get_relevant_documents(self, query: str, *, run_manager=None) -> list[Document]:
        results = self._service.search(query, department=self.department, doc_type=self.doc_type)
        return [
            Document(
                page_content=str(item["content"]),
                metadata={
                    "doc_id": item["doc_id"],
                    "source_file": item["source_file"],
                    "page_num": item["page_num"],
                    "department": item["department"],
                    "doc_type": item["doc_type"],
                    "score": item["score"],
                },
            )
            for item in results
        ]

    async def _aget_relevant_documents(self, query: str, *, run_manager=None) -> list[Document]:
        return self._get_relevant_documents(query, run_manager=run_manager)


def format_documents(documents: list[Document]) -> str:
    """把文档格式化为可读上下文。"""
    return "\n\n".join(
        f"[{doc.metadata.get('source_file')} 第{doc.metadata.get('page_num')}段] {doc.page_content}" for doc in documents
    )


# 历史版本查询意图关键词
_HISTORY_LOOKUP_KEYWORDS = {
    "旧版本", "历史版本", "作废制度", "旧规则", "过期制度",
    "deprecated", "已过期", "已作废", "v1.0", "v2.0", "2023年", "2024年",
}


def _detect_history_lookup(query: str) -> bool:
    """检测用户查询是否包含历史版本/旧制度查询意图。

    当用户明确询问旧版本、作废制度、过期规则等内容时，系统自动开启
    history_lookup 模式，放宽 is_latest 和 deprecated 过滤，允许命中历史数据。

    参数：
    - query: 用户原始查询字符串。

    返回值：
    True 表示命中历史版本意图，应开启 history_lookup；
    False 表示未命中，使用默认过滤（只检索最新 active 文档）。
    """
    lowered = query.lower()
    for keyword in _HISTORY_LOOKUP_KEYWORDS:
        if keyword.lower() in lowered:
            return True
    return False


async def run_retrieval_pipeline(
    query: str,
    *,
    user: CurrentUser | None = None,
    vectorstore: KnowledgeVectorStore | None = None,
    history_lookup: bool = False,
) -> KnowledgeAnswerPayload:
    """执行企业 RAG 检索链路。

    本函数是新的检索链路核心入口，按以下顺序执行：
    1. Query Rewrite：调用 QueryRewriteService 做轻量改写与关键词提取；
    2. ACL：调用 resolve_access_policy 把用户上下文转为统一过滤条件；
    3. Hybrid Retrieval：调用 KnowledgeVectorStore.search 执行 dense+sparse 检索、
       RRF 融合与 rerank 精排；
    4. Citation 打包：把候选 chunk 转为 CitationItem 列表；
    5. Grounded Answer：把 Top-K chunk 拼入 prompt，调用 LLM 生成带依据的回答；
    6. Debug Trace：把各阶段结果写入 RetrievalDebugTrace，供排障使用。

    参数说明：
    - query: 用户原始查询字符串；
    - user: 当前用户上下文，用于 ACL 解析。为 None 时使用开放策略；
    - vectorstore: 外部传入的 KnowledgeVectorStore 实例，用于测试注入。
      为 None 时新建实例（生产环境需先完成索引加载）；
    - history_lookup: 是否开启历史版本查询模式，默认 False。

    返回值：
    KnowledgeAnswerPayload，包含 answer、citations、retrieval_debug，
    供下游节点和 API 路由统一消费。
    """
    # 1. Query Rewrite
    rewrite_service = QueryRewriteService()
    rewrite_result = rewrite_service.rewrite(query)

    # 自动检测历史版本查询意图：若用户明确询问旧版本/作废制度，开启 history_lookup
    if not history_lookup:
        history_lookup = _detect_history_lookup(query)

    # 2. ACL
    access_policy = resolve_access_policy(user) if user is not None else None

    # 3. Hybrid Retrieval + Fallback
    vs = vectorstore or KnowledgeVectorStore()

    def _execute_search(rewrite: QueryRewriteResult) -> list[dict[str, Any]]:
        """封装单次检索调用，供 fallback 阶段复用。"""
        return vs.search(
            rewrite.rewritten_query or query,
            keywords=rewrite.keywords or None,
            access_policy=access_policy,
            history_lookup=history_lookup,
        )

    candidates = _execute_search(rewrite_result)
    fallback_triggered = ""
    low_recall_threshold = 5

    # Fallback 1：rewrite retry
    if len(candidates) < low_recall_threshold and rewrite_service.should_retry(rewrite_result, len(candidates)):
        rewrite_result = rewrite_service.rewrite(query, retry_count=rewrite_result.retry_count + 1)
        candidates = _execute_search(rewrite_result)
        fallback_triggered = "rewrite_retry"

    # Fallback 2：升档（只升级 1 档 retrieval profile）
    if len(candidates) < low_recall_threshold:
        vs.upscale_for_next_search()
        candidates = _execute_search(rewrite_result)
        fallback_triggered = "upscale"

    # Fallback 3：HyDE（若命中白名单且仍低召回）
    # 首版仅实现白名单判定与触发标记，实际假设文档扩写需接入 LLM 生成
    # 后接二次向量检索，待后续模型能力完备后补齐。
    if len(candidates) < low_recall_threshold and is_hyde_eligible(query):
        fallback_triggered = "hyde"

    # 4. Citation 打包
    citations: list[CitationItem] = []
    for c in candidates:
        citations.append(
            CitationItem(
                doc_id=str(c.get("doc_id", "")),
                chunk_id=str(c.get("chunk_id", "")),
                source_file=str(c.get("source_file", "")),
                section_path=str(c.get("section_path", "")),
                version="",
                snippet=str(c.get("snippet", "")),
            )
        )

    # 5. Grounded Answer（首版简化）
    answer = ""
    if candidates:
        context_chunks = []
        for c in candidates[:5]:
            src = c.get("source_file", "")
            sec = c.get("section_path", "")
            ref = f"[{src} {sec}]" if sec else f"[{src}]"
            context_chunks.append(f"{ref} {c.get('content', '')}")
        context = "\n\n".join(context_chunks)

        llm = get_chat_model(temperature=0.1, tags=["rag_answer"])
        if llm is not None:
            prompt = ChatPromptTemplate.from_template(
                "你是企业知识库助手。请只依据给定上下文回答。\n\n问题：{question}\n\n上下文：\n{context}"
            )
            chain = prompt | llm | StrOutputParser()
            answer = await chain.ainvoke({"question": query, "context": context})

    # 6. Debug Trace
    debug = RetrievalDebugTrace(
        original_query=query,
        rewritten_query=rewrite_result.rewritten_query,
        profile="standard",
        reranked_top=candidates,
        low_recall=len(candidates) < low_recall_threshold,
        low_confidence=len(candidates) < 3,
        rewrite_retry_count=rewrite_result.retry_count,
        fallback_triggered=fallback_triggered,
        history_lookup=history_lookup,
    )

    return KnowledgeAnswerPayload(
        answer=answer,
        citations=citations,
        retrieval_debug=debug,
    )


async def run_rag_chain(query: str, *, department: str | None = None, doc_type: str | None = None) -> dict[str, Any]:
    """执行 RAG 检索链（兼容层）。

    本函数保留旧接口签名，供 knowledge_rag_node 等上游节点调用。
    内部委托给 run_retrieval_pipeline，然后把 KnowledgeAnswerPayload 转回旧格式。

    参数：
    - query: 用户查询字符串；
    - department: 兼容旧参数，当前版本已纳入 ACL 统一处理，此处忽略；
    - doc_type: 兼容旧参数，当前版本已纳入 ACL 统一处理，此处忽略。

    返回值：
    旧格式 dict，包含 answer、documents、sources，供现有节点兼容消费。
    """
    payload = await run_retrieval_pipeline(query)

    # 把新格式的 citations 转回旧 sources 格式
    sources = [
        {
            "doc_id": c.doc_id,
            "source_file": c.source_file,
            "page_num": 1,
            "department": "",
            "score": 0.0,
            "snippet": c.snippet,
        }
        for c in payload.citations
    ]

    # 把 citations 转回旧 documents 格式
    documents = [
        Document(
            page_content=c.snippet,
            metadata={
                "doc_id": c.doc_id,
                "source_file": c.source_file,
                "page_num": 1,
                "department": "",
                "doc_type": "",
                "score": 0.0,
            },
        )
        for c in payload.citations
    ]

    return {
        "answer": payload.answer,
        "documents": documents,
        "sources": sources,
    }
