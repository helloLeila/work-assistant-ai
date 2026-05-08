"""商旅服务测试。"""

from __future__ import annotations

import httpx

from app.core.config import get_settings
from app.services.travel_service import get_travel_service
from app.models.domain import TravelInfo


def test_travel_service_falls_back_to_local_order_when_provider_not_configured(monkeypatch) -> None:
    """未配置外部接口时应返回本地下单结果。"""
    monkeypatch.delenv("TRAVEL_API_BASE_URL", raising=False)
    get_settings.cache_clear()
    get_travel_service.cache_clear()

    order = get_travel_service().create_order(
        TravelInfo(
            from_city="上海",
            to_city="深圳",
            date="2026-05-12",
            passengers=2,
            cabin_class="商务舱",
        )
    )

    assert order.provider == "local"
    assert order.status == "confirmed"
    assert "上海 -> 深圳" in order.itinerary_summary


def test_travel_service_forwards_request_to_provider_when_configured(monkeypatch) -> None:
    """配置第三方接口后应优先执行转发。"""
    monkeypatch.setenv("TRAVEL_API_BASE_URL", "https://travel.example.com")
    monkeypatch.setenv("TRAVEL_API_PATH", "/api/orders")
    monkeypatch.setenv("TRAVEL_API_AUTH_TOKEN", "secret-token")
    get_settings.cache_clear()
    get_travel_service.cache_clear()

    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "order_id": "EXT-10001",
                "status": "submitted",
                "itinerary_summary": "2026-05-20 上海 -> 北京，1位乘客，经济舱",
                "booking_reference": "BK-7788",
                "provider": "travel.example.com",
            }

    def fake_post(url: str, *, json: dict[str, object], headers: dict[str, str], timeout: float) -> FakeResponse:
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(httpx, "post", fake_post)

    order = get_travel_service().create_order(
        TravelInfo(
            from_city="上海",
            to_city="北京",
            date="2026-05-20",
            passengers=1,
            cabin_class="经济舱",
        )
    )

    assert captured["url"] == "https://travel.example.com/api/orders"
    assert captured["json"] == {
        "from_city": "上海",
        "to_city": "北京",
        "date": "2026-05-20",
        "passengers": 1,
        "cabin_class": "经济舱",
    }
    assert captured["headers"] == {
        "Authorization": "Bearer secret-token",
        "Content-Type": "application/json",
    }
    assert captured["timeout"] == 10.0
    assert order.order_id == "EXT-10001"
    assert order.provider == "travel.example.com"
