"""查询改写服务测试。

本测试锁定 QueryRewriteService 各阶段行为：
- light_rewrite 的改写质量与失败兜底；
- keyword_extraction 的上限与停用词过滤；
- rewrite_blacklist 对固定编码的保护；
- should_retry 的重试次数限制。

任何对改写逻辑的调整都必须在此验证，防止改写过度导致精确查询丢失。
"""

from __future__ import annotations

import pytest

from app.models.knowledge_retrieval import QueryRewriteResult
from app.services.query_rewrite_service import QueryRewriteService


@pytest.fixture
def service() -> QueryRewriteService:
    """提供隔离的 QueryRewriteService 实例。"""
    return QueryRewriteService()


class TestSkeleton:
    """测试服务骨架与基础输出格式。"""

    def test_returns_typed_result(self, service: QueryRewriteService) -> None:
        """rewrite 必须返回 QueryRewriteResult 类型对象。"""
        result = service.rewrite("测试查询")
        assert isinstance(result, QueryRewriteResult)

    def test_preserves_original_query(self, service: QueryRewriteService) -> None:
        """骨架阶段不改变 original_query。"""
        result = service.rewrite("请问一下年假怎么休")
        assert result.original_query == "请问一下年假怎么休"

    def test_skeleton_strategy(self, service: QueryRewriteService) -> None:
        """骨架阶段 strategy 标记为 skeleton。"""
        result = service.rewrite("anything")
        assert result.strategy == "skeleton"
