"""商旅代办节点。"""

from __future__ import annotations

from app.chains.extraction_chain import extract_travel_info
from app.models.domain import TravelOrder
from app.tools.travel_api_tool import get_travel_booking_tool


async def travel_booking_node(state: dict) -> dict:
    """抽取商旅信息并创建订单。"""
    travel_info = await extract_travel_info(state["query"])
    payload = travel_info.model_dump_json()
    order = TravelOrder.model_validate_json(get_travel_booking_tool().invoke(payload))
    return {
        "travel_info": travel_info.model_dump(),
        "structured_data": {"travel_order": order.model_dump()},
    }
