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
        """rewrite 不改变 original_query。"""
        result = service.rewrite("请问一下年假怎么休")
        assert result.original_query == "请问一下年假怎么休"

    def test_strategy_no_change(self, service: QueryRewriteService) -> None:
        """未触发改写时 strategy 标记为 no_change。"""
        result = service.rewrite("anything")
        assert result.strategy == "no_change"


class TestLightRewrite:
    """测试轻量规则改写与失败兜底。"""

    def test_removes_polite_prefix(self, service: QueryRewriteService) -> None:
        """去除常见口语前缀。"""
        result = service.rewrite("请问一下年假怎么休")
        assert result.rewritten_query == "年假 休假 流程"
        assert result.strategy == "light_rewrite"

    def test_replaces_suffix(self, service: QueryRewriteService) -> None:
        """把口语后缀替换为制度类关键词。"""
        result = service.rewrite("报销怎么做")
        assert result.rewritten_query == "报销 流程"
        assert result.strategy == "light_rewrite"

    def test_fallback_on_exception(self, service: QueryRewriteService, monkeypatch) -> None:
        """_light_rewrite 抛异常时回退原 query。"""
        from app.services import query_rewrite_service

        def raise_error(q: str) -> str:
            raise RuntimeError("rewrite error")

        monkeypatch.setattr(query_rewrite_service, "_light_rewrite", raise_error)
        result = service.rewrite("年假怎么休")
        assert result.rewritten_query == "年假怎么休"
        assert result.strategy == "no_change"


class TestKeywordExtraction:
    """测试关键词提取规范。"""

    def test_extracts_keywords(self, service: QueryRewriteService) -> None:
        """从改写后文本提取关键词。"""
        result = service.rewrite("请问一下报销怎么做")
        assert "报销" in result.keywords
        assert "流程" in result.keywords

    def test_limits_to_five_keywords(self, service: QueryRewriteService) -> None:
        """关键词数量不超过 5 个。"""
        result = service.rewrite("第一条 第二条 第三条 第四条 第五条 第六条")
        assert len(result.keywords) <= 5

    def test_filters_stop_words(self, service: QueryRewriteService) -> None:
        """停用词和虚词不参与关键词提取。"""
        result = service.rewrite("请问一下怎么报销")
        # "请问"、"一下"、"怎么" 应为停用词
        assert "请问" not in result.keywords
        assert "一下" not in result.keywords
        assert "怎么" not in result.keywords
