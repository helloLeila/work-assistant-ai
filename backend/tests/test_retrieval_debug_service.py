"""检索调试服务测试。

本测试锁定 RetrievalDebugService 的 trace 封装行为：
- build_trace 必须返回 RetrievalDebugTrace 类型；
- 各阶段中间结果（dense/sparse/RRF/rerank）应完整透传；
- 未提供的字段应使用安全默认值，不导致解析失败。

任何对调试追踪结构的调整都必须在此验证，防止排障字段丢失。
"""

from __future__ import annotations

import pytest

from app.models.knowledge_retrieval import (
    BiasMode,
    RetrievalDebugTrace,
    RetrievalProfile,
)
from app.services.retrieval_debug_service import RetrievalDebugService


@pytest.fixture
def service() -> RetrievalDebugService:
    """提供隔离的 RetrievalDebugService 实例。"""
    return RetrievalDebugService()


class TestBuildTrace:
    """测试 trace 封装核心行为。"""

    def test_returns_typed_trace(self, service: RetrievalDebugService) -> None:
        """build_trace 必须返回 RetrievalDebugTrace 类型。"""
        trace = service.build_trace(original_query="报销")
        assert isinstance(trace, RetrievalDebugTrace)

    def test_preserves_original_and_rewritten_query(
        self, service: RetrievalDebugService
    ) -> None:
        """原始查询与改写查询应完整透传。"""
        trace = service.build_trace(
            original_query="请问一下报销怎么做",
            rewritten_query="报销 流程",
        )
        assert trace.original_query == "请问一下报销怎么做"
        assert trace.rewritten_query == "报销 流程"

    def test_records_acl_and_profile(self, service: RetrievalDebugService) -> None:
        """ACL 过滤与检索档位应被记录。"""
        trace = service.build_trace(
            original_query="test",
            acl_filter="department == 'HR'",
            profile=RetrievalProfile.HIGH_RECALL,
            bias_mode=BiasMode.SEMANTIC_BIAS,
        )
        assert trace.acl_filter == "department == 'HR'"
        assert trace.profile == RetrievalProfile.HIGH_RECALL
        assert trace.bias_mode == BiasMode.SEMANTIC_BIAS


class TestStageCandidates:
    """测试各阶段候选列表记录。"""

    def test_records_dense_candidates(self, service: RetrievalDebugService) -> None:
        """dense 检索候选应被记录。"""
        trace = service.build_trace(
            original_query="test",
            dense_candidates=[
                {"doc_id": "d1", "score": 0.92},
                {"doc_id": "d2", "score": 0.85},
            ],
        )
        assert len(trace.dense_candidates) == 2
        assert trace.dense_candidates[0]["score"] == 0.92

    def test_records_sparse_candidates(self, service: RetrievalDebugService) -> None:
        """sparse 检索候选应被记录。"""
        trace = service.build_trace(
            original_query="test",
            sparse_candidates=[
                {"doc_id": "d1", "score": 0.75},
            ],
        )
        assert len(trace.sparse_candidates) == 1
        assert trace.sparse_candidates[0]["doc_id"] == "d1"

    def test_records_rrf_merged(self, service: RetrievalDebugService) -> None:
        """RRF 融合结果应被记录。"""
        trace = service.build_trace(
            original_query="test",
            rrf_merged=[
                {"doc_id": "d1", "score": 0.016},
                {"doc_id": "d2", "score": 0.014},
            ],
        )
        assert len(trace.rrf_merged) == 2
        assert trace.rrf_merged[1]["score"] == 0.014

    def test_records_reranked_top(self, service: RetrievalDebugService) -> None:
        """rerank 精排结果应被记录。"""
        trace = service.build_trace(
            original_query="test",
            reranked_top=[
                {"doc_id": "d1", "score": 0.88},
            ],
        )
        assert len(trace.reranked_top) == 1
        assert trace.reranked_top[0]["score"] == 0.88

    def test_all_stages_together(self, service: RetrievalDebugService) -> None:
        """同时提供多阶段候选时各列表独立记录。"""
        trace = service.build_trace(
            original_query="test",
            dense_candidates=[{"doc_id": "d1", "score": 0.9}],
            sparse_candidates=[{"doc_id": "d1", "score": 0.5}],
            rrf_merged=[{"doc_id": "d1", "score": 0.016}],
            reranked_top=[{"doc_id": "d1", "score": 0.8}],
        )
        assert len(trace.dense_candidates) == 1
        assert len(trace.sparse_candidates) == 1
        assert len(trace.rrf_merged) == 1
        assert len(trace.reranked_top) == 1


class TestMetadataFlags:
    """测试元信息标记记录。"""

    def test_records_retry_and_fallback(self, service: RetrievalDebugService) -> None:
        """改写重试次数与 fallback 动作应被记录。"""
        trace = service.build_trace(
            original_query="test",
            rewrite_retry_count=1,
            fallback_triggered="upscale",
        )
        assert trace.rewrite_retry_count == 1
        assert trace.fallback_triggered == "upscale"

    def test_records_recall_and_confidence(self, service: RetrievalDebugService) -> None:
        """低召回与低置信度标记应被记录。"""
        trace = service.build_trace(
            original_query="test",
            low_recall=True,
            low_confidence=True,
        )
        assert trace.low_recall is True
        assert trace.low_confidence is True

    def test_records_history_lookup(self, service: RetrievalDebugService) -> None:
        """history_lookup 状态应被记录。"""
        trace = service.build_trace(
            original_query="旧版本报销规定",
            history_lookup=True,
        )
        assert trace.history_lookup is True


class TestDefaults:
    """测试默认值安全性。"""

    def test_defaults_when_only_original_query(self, service: RetrievalDebugService) -> None:
        """仅提供 original_query 时其余字段使用安全默认值。"""
        trace = service.build_trace(original_query="q")
        assert trace.rewritten_query == ""
        assert trace.acl_filter == ""
        assert trace.profile == RetrievalProfile.STANDARD
        assert trace.bias_mode == BiasMode.BALANCED
        assert trace.dense_candidates == []
        assert trace.sparse_candidates == []
        assert trace.rrf_merged == []
        assert trace.reranked_top == []
        assert trace.low_recall is False
        assert trace.low_confidence is False
        assert trace.rewrite_retry_count == 0
        assert trace.fallback_triggered == ""
        assert trace.history_lookup is False

    def test_none_candidates_default_to_empty_list(
        self, service: RetrievalDebugService
    ) -> None:
        """显式传入 None 作为候选列表时应回退为空列表。"""
        trace = service.build_trace(
            original_query="test",
            dense_candidates=None,
            sparse_candidates=None,
            rrf_merged=None,
            reranked_top=None,
        )
        assert trace.dense_candidates == []
        assert trace.sparse_candidates == []
        assert trace.rrf_merged == []
        assert trace.reranked_top == []
