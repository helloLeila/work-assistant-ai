"""联网搜索节点测试。"""

from __future__ import annotations

import asyncio

from app.models.domain import WebSearchHit, WebSearchResult
from app.nodes.web_search_node import web_search_node


def test_weather_query_without_city_returns_clarifying_message() -> None:
    """只有“天气”且拿不到定位时，不应把全国天气杂糅结果直接喂给模型。"""
    result = asyncio.run(
        web_search_node(
            {
                "query": "天气",
            }
        )
    )

    assert "具体城市" in result["structured_data"]["message"]


def test_weather_query_with_ip_uses_augmented_city_search(monkeypatch) -> None:
    """天气类请求在拿到公网 IP 后，应自动补全城市再搜索。"""
    import app.nodes.web_search_node as web_search_module

    class FakeIPLocationService:
        async def lookup(self, ip: str) -> str | None:
            assert ip == "8.8.8.8"
            return "深圳"

    captured: dict[str, str] = {}

    class FakeWebSearchService:
        async def search(
            self,
            query: str,
            *,
            max_results: int | None = None,
            freshness: str | None = None,
        ) -> WebSearchResult:
            captured["query"] = query
            captured["freshness"] = freshness or ""
            return WebSearchResult(
                query=query,
                results=[
                    WebSearchHit(
                        title="深圳天气预报",
                        url="https://weather.example.com/shenzhen",
                        snippet="2026年05月16日深圳天气预报：多云，温度:26/20°C，南风3级，空气质量优。",
                        site_name="天气网",
                    )
                ],
            )

    monkeypatch.setenv("BOCHA_API_KEY", "dummy-key")
    monkeypatch.setattr(web_search_module, "get_ip_location_service", lambda: FakeIPLocationService())
    monkeypatch.setattr(web_search_module, "get_web_search_service", lambda: FakeWebSearchService())

    result = asyncio.run(
        web_search_node(
            {
                "query": "天气",
                "client_ip": "8.8.8.8",
            }
        )
    )

    assert captured["query"] == "深圳 天气"
    assert captured["freshness"] == "oneDay"
    assert result["structured_data"]["weather_report"]["city"] == "深圳"
    assert result["structured_data"]["weather_report"]["forecast_date"] == "2026-05-16"
    assert "深圳" in result["structured_data"]["message"]
    assert "多云" in result["structured_data"]["message"]
    assert "南风3级" in result["structured_data"]["message"]
    assert "空气质量优" in result["structured_data"]["message"]


def test_weather_query_discards_stale_results(monkeypatch) -> None:
    """摘要里的天气日期已过期时，应拒绝作为最新天气展示。"""
    import app.nodes.web_search_node as web_search_module

    class FakeWebSearchService:
        async def search(
            self,
            query: str,
            *,
            max_results: int | None = None,
            freshness: str | None = None,
        ) -> WebSearchResult:
            return WebSearchResult(
                query=query,
                results=[
                    WebSearchHit(
                        title="深圳天气预报",
                        url="https://weather.example.com/shenzhen",
                        snippet=(
                            "2026年04月25日深圳天气预报: 04/25 (周六): 天气:多云转晴,"
                            "温度:26/20°C,风向风力:无持续风向<3级"
                        ),
                        site_name="天气网",
                    )
                ],
            )

    monkeypatch.setenv("BOCHA_API_KEY", "dummy-key")
    monkeypatch.setattr(web_search_module, "get_web_search_service", lambda: FakeWebSearchService())

    result = asyncio.run(
        web_search_node(
            {
                "query": "深圳天气",
            }
        )
    )

    assert "可信的最新天气数据" in result["structured_data"]["message"]
