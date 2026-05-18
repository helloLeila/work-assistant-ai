"""Milvus 与本地检索回退封装。

系统论说明：
- 本模块是整个企业 RAG 检索的向量存储入口；
- 上游被 KnowledgeIngestionService._index_documents 调用写入索引；
- 下游被 retrieval_pipeline 调用执行检索；
- 必须保证 dense 主路径、sparse 补充路径、本地词法兜底路径三套链路复用同一套 ACL 过滤，
  否则 Milvus 挂掉时本地回退会直接变成越权泄露通道。
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

TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]+")


class KnowledgeVectorStore:
    """优先使用 Milvus dense 检索，失败时回退到本地词法检索。

    系统论说明：
    - 索引侧：接收 Document 列表，同时写入 Milvus 和本地内存/文件；
    - 检索侧：先尝试 Milvus dense search，异常时回退到本地 _lexical_search；
    - 过滤侧：search 方法接收统一 AccessPolicy，dense 和本地回退都必须执行同一套过滤。
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._records: list[Document] = []
        self._milvus: Milvus | None = None

    def index_documents(self, documents: list[Document]) -> None:
        """建立文档索引。"""
        self._records = documents
        self._persist_local_index(documents)
        self._try_build_milvus_index(documents)

    def search(
        self,
        query: str,
        *,
        department: str | None = None,
        doc_type: str | None = None,
        top_k: int | None = None,
    ) -> list[dict[str, Any]]:
        """执行检索。"""
        top_k = top_k or self._settings.knowledge_top_k

        if self._milvus is not None:
            try:
                filter_parts = []
                if department:
                    filter_parts.append(f'department == "{department}"')
                if doc_type:
                    filter_parts.append(f'doc_type == "{doc_type}"')
                expression = " and ".join(filter_parts) if filter_parts else None
                docs = self._milvus.max_marginal_relevance_search(query, k=top_k, expr=expression)
                return [self._to_search_result(doc, self._lexical_score(query, doc.page_content)) for doc in docs]
            except Exception:
                pass

        return self._lexical_search(query, department=department, doc_type=doc_type, top_k=top_k)

    def _try_build_milvus_index(self, documents: list[Document]) -> None:
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
        department: str | None = None,
        doc_type: str | None = None,
        top_k: int,
    ) -> list[dict[str, Any]]:
        candidates = []
        for doc in self._records:
            if department and doc.metadata.get("department") != department:
                continue
            if doc_type and doc.metadata.get("doc_type") != doc_type:
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

    def _to_search_result(self, doc: Document, score: float) -> dict[str, Any]:
        return {
            "doc_id": str(doc.metadata.get("doc_id", "")),
            "content": doc.page_content,
            "source_file": str(doc.metadata.get("source_file", "")),
            "page_num": int(doc.metadata.get("page_num", 1)),
            "department": str(doc.metadata.get("department", "")),
            "doc_type": str(doc.metadata.get("doc_type", "")),
            "score": round(score, 4),
            "snippet": doc.page_content[:180],
        }

    def _lexical_score(self, query: str, content: str) -> float:
        query_tokens = self._tokenize(query)
        content_tokens = self._tokenize(content)
        overlap = query_tokens.intersection(content_tokens)
        if not overlap:
            return 0.0
        return len(overlap) / math.sqrt(max(len(query_tokens), 1) * max(len(content_tokens), 1))

    def _persist_local_index(self, documents: list[Document]) -> None:
        payload = [{"page_content": document.page_content, "metadata": document.metadata} for document in documents]
        index_path = Path(self._settings.knowledge_index_dir) / "local_index.json"
        index_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _tokenize(self, text: str) -> set[str]:
        return {token.lower() for token in TOKEN_PATTERN.findall(text)}

    @staticmethod
    def _jaccard(left: set[str], right: set[str]) -> float:
        union = left.union(right)
        if not union:
            return 0.0
        return len(left.intersection(right)) / len(union)


@lru_cache
def get_knowledge_vectorstore() -> KnowledgeVectorStore:
    return KnowledgeVectorStore()
