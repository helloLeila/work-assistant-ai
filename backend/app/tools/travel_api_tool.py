"""商旅 API 工具。"""

from __future__ import annotations

from functools import lru_cache

from langchain_core.tools import Tool

from app.models.domain import TravelInfo
from app.services.travel_service import get_travel_service


def _create_order(payload: str) -> str:
    """把结构化参数转成真实订单结果。"""
    travel_info = TravelInfo.model_validate_json(payload)
    order = get_travel_service().create_order(travel_info)
    return order.model_dump_json()


@lru_cache
def get_travel_booking_tool() -> Tool:
    """返回商旅预订工具。"""
    return Tool(
        name="travel_booking_tool",
        description="根据结构化商旅信息创建一笔出行订单，并在有配置时转发到外部商旅系统。",
        func=_create_order,
    )
