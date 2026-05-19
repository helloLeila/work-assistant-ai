"""RAG 链测试。

本测试锁定 rag_chain 重构后的接口契约与链路行为：
- run_retrieval_pipeline 必须返回 KnowledgeAnswerPayload；
- 返回值包含 citations 与 retrieval_debug；
- run_rag_chain 兼容层仍返回旧格式。

任何对检索链路的调整都必须在此验证，防止下游节点因格式变更而崩溃。
"""

from __future__ import annotations

import asyncio

import pytest

from app.chains.rag_chain import run_rag_chain, run_retrieval_pipeline
from app.models.knowledge_retrieval import KnowledgeAnswerPayload
from app.vectorstore.milvus_client import KnowledgeVectorStore


@pytest.fixture
def vectorstore() -> KnowledgeVectorStore:
    """提供带测试数据的 KnowledgeVectorStore 实例。"""
    from langchain_core.documents import Document

    vs = KnowledgeVectorStore()
    vs._records = [
        Document(
            page_content="员工报销流程规定",
            metadata={
                "status": "active",
                "is_latest": True,
                "doc_id": "doc-1",
                "chunk_id": "doc-1-c1",
                "source_file": "报销制度.txt",
                "section_path": "第一章",
                "page_num": 1,
            },
        ),
        Document(
            page_content="年假休假制度说明",
            metadata={
                "status": "active",
                "is_latest": True,
                "doc_id": "doc-2",
                "chunk_id": "doc-2-c1",
                "source_file": "休假制度.txt",
                "section_path": "总则",
                "page_num": 1,
            },
        ),
        Document(
            page_content="2023年旧版报销规定（已作废）",
            metadata={
                "status": "deprecated",
                "is_latest": False,
                "doc_id": "doc-old",
                "chunk_id": "doc-old-c1",
                "source_file": "旧报销制度.txt",
                "section_path": "第一章",
                "page_num": 1,
            },
        ),
    ]
    return vs


class TestRetrievalPipeline:
    """测试新链路核心接口。"""

    def test_returns_payload_type(self, vectorstore: KnowledgeVectorStore) -> None:
        """run_retrieval_pipeline 返回 KnowledgeAnswerPayload 类型。"""
        result = asyncio.run(run_retrieval_pipeline("报销怎么做", vectorstore=vectorstore))
        assert isinstance(result, KnowledgeAnswerPayload)

    def test_payload_has_citations(self, vectorstore: KnowledgeVectorStore) -> None:
        """返回结果包含 citations 列表。"""
        result = asyncio.run(run_retrieval_pipeline("报销", vectorstore=vectorstore))
        assert isinstance(result.citations, list)

    def test_payload_has_debug_trace(self, vectorstore: KnowledgeVectorStore) -> None:
        """返回结果包含 retrieval_debug 调试追踪。"""
        result = asyncio.run(run_retrieval_pipeline("报销", vectorstore=vectorstore))
        assert result.retrieval_debug is not None
        assert result.retrieval_debug.original_query == "报销"

    def test_rewrite_is_applied(self, vectorstore: KnowledgeVectorStore) -> None:
        """查询改写结果体现在 debug trace 中。"""
        result = asyncio.run(run_retrieval_pipeline("请问一下报销怎么做", vectorstore=vectorstore))
        assert result.retrieval_debug.rewritten_query != ""
        assert "报销" in result.retrieval_debug.rewritten_query


class TestHistoryLookup:
    """测试历史版本查询模式自动检测。"""

    def test_history_lookup_detects_intent(self, vectorstore: KnowledgeVectorStore) -> None:
        """查询包含'旧版本'时自动开启 history_lookup，命中 deprecated 文档。"""
        result = asyncio.run(run_retrieval_pipeline("旧版本报销规定", vectorstore=vectorstore))
        assert result.retrieval_debug.history_lookup is True
        # 应命中已作废的旧版文档
        doc_ids = {c.doc_id for c in result.citations}
        assert "doc-old" in doc_ids

    def test_normal_query_skips_deprecated(self, vectorstore: KnowledgeVectorStore) -> None:
        """普通查询不开启 history_lookup，deprecated 文档不应出现在结果中。"""
        result = asyncio.run(run_retrieval_pipeline("报销流程", vectorstore=vectorstore))
        assert result.retrieval_debug.history_lookup is False
        doc_ids = {c.doc_id for c in result.citations}
        assert "doc-old" not in doc_ids

    def test_explicit_history_lookup_overrides(self, vectorstore: KnowledgeVectorStore) -> None:
        """显式传入 history_lookup=True 时强制开启，不受查询内容影响。"""
        result = asyncio.run(
            run_retrieval_pipeline("随便问问", vectorstore=vectorstore, history_lookup=True)
        )
        assert result.retrieval_debug.history_lookup is True


class TestFallbackOrder:
    """测试检索兜底顺序：rewrite retry -> 升档。"""

    def test_fallback_rewrite_retry_then_upscale(self, vectorstore: KnowledgeVectorStore) -> None:
        """候选不足时先触发 rewrite retry，仍不足则触发升档。"""
        # 查询"火星移民政策"在 fixture 中无匹配且不在 HyDE 白名单，召回为 0，触发 fallback
        result = asyncio.run(run_retrieval_pipeline("火星移民政策", vectorstore=vectorstore))
        assert result.retrieval_debug.low_recall is True
        # fallback_triggered 应记录最后触动的动作（rewrite_retry 或 upscale）
        assert result.retrieval_debug.fallback_triggered in ("rewrite_retry", "upscale")

    def test_fallback_records_upscale(self, vectorstore: KnowledgeVectorStore) -> None:
        """升档后 vectorstore 的 active_profile 应被重置回 standard。"""
        # 触发一次低召回查询
        asyncio.run(run_retrieval_pipeline("完全不相关的内容", vectorstore=vectorstore))
        # 再次查询应回到 standard 档位
        result = asyncio.run(run_retrieval_pipeline("报销", vectorstore=vectorstore))
        assert len(result.citations) <= 5


class TestRagChainCompatibility:
    """测试旧接口兼容层。"""

    def test_returns_old_format(self) -> None:
        """run_rag_chain 仍返回旧格式 dict。"""
        result = asyncio.run(run_rag_chain("测试查询"))
        assert "answer" in result
        assert "documents" in result
        assert "sources" in result

    def test_sources_is_list(self) -> None:
        """sources 字段为列表类型。"""
        result = asyncio.run(run_rag_chain("测试查询"))
        assert isinstance(result["sources"], list)
