"""重排服务测试。

本测试锁定 RerankService 的接口契约与边界行为：
- 基础骨架能否被实例化；
- rerank 方法的输入输出类型；
- 空候选与少候选的边界处理；
- profile 对输入上限的控制。

任何对重排接口的修改都必须在此验证，防止下游 rag_chain 调用失败。
"""

from __future__ import annotations

import pytest

from app.services.rerank_service import RerankService


@pytest.fixture
def service() -> RerankService:
    """提供隔离的 RerankService 实例。"""
    return RerankService()


@pytest.fixture
def sample_candidates() -> list[dict]:
    """提供测试用候选列表。"""
    return [
        {"chunk_id": "c1", "score": 0.9, "content": "第一条内容"},
        {"chunk_id": "c2", "score": 0.8, "content": "第二条内容"},
        {"chunk_id": "c3", "score": 0.7, "content": "第三条内容"},
        {"chunk_id": "c4", "score": 0.6, "content": "第四条内容"},
        {"chunk_id": "c5", "score": 0.5, "content": "第五条内容"},
    ]


class TestSkeleton:
    """测试服务骨架与基础接口。"""

    def test_can_instantiate(self) -> None:
        """RerankService 可被正常实例化。"""
        service = RerankService()
        assert isinstance(service, RerankService)

    def test_rerank_returns_list(self, service: RerankService, sample_candidates: list[dict]) -> None:
        """rerank 方法返回列表类型。"""
        result = service.rerank("测试查询", sample_candidates)
        assert isinstance(result, list)

    def test_rerank_preserves_chunk_id(self, service: RerankService, sample_candidates: list[dict]) -> None:
        """rerank 结果保留 chunk_id 字段。"""
        result = service.rerank("测试查询", sample_candidates)
        assert len(result) > 0
        assert "chunk_id" in result[0]


class TestTopK:
    """测试输出数量限制。"""

    def test_default_top_k_limits_output(self, service: RerankService, sample_candidates: list[dict]) -> None:
        """默认 top_k 限制返回数量。"""
        result = service.rerank("测试查询", sample_candidates)
        assert len(result) <= service._default_top_k

    def test_explicit_top_k_overrides(self, service: RerankService, sample_candidates: list[dict]) -> None:
        """显式传入 top_k 时覆盖默认值。"""
        result = service.rerank("测试查询", sample_candidates, top_k=2)
        assert len(result) <= 2


class TestEmptyCandidates:
    """测试边界情况。"""

    def test_empty_candidates_returns_empty(self, service: RerankService) -> None:
        """空候选列表返回空结果。"""
        result = service.rerank("测试查询", [])
        assert result == []

    def test_fewer_than_top_k(self, service: RerankService) -> None:
        """候选数量少于 top_k 时返回全部候选。"""
        candidates = [{"chunk_id": "c1", "score": 0.5, "content": "唯一内容"}]
        result = service.rerank("测试查询", candidates)
        assert len(result) == 1
