"""个人信息节点。"""

from __future__ import annotations

from app.chains.extraction_chain import extract_personal_query
from app.services.personal_info_service import get_personal_info_service
from app.tools.personal_info_tool import get_personal_info_tool


async def personal_info_node(state: dict) -> dict:
    """执行个人信息查询。"""
    current_user = state["current_user"]
    target_user_id = state["target_user_id"]
    parsed = await extract_personal_query(state["query"])
    tool_payload = f"{current_user.user_id}|{target_user_id}"
    _ = get_personal_info_tool().invoke(tool_payload)
    personal_data = get_personal_info_service().get_personal_info(current_user, target_user_id)
# 根据解析结果过滤个人信息字段，默认返回全部字段；
# 如果 requested_fields 有值，
# 则只返回其中指定的字段（加上 user_id 和 name 以便确认身份）。
# 这样做可以避免过度暴露个人信息，同时满足用户的特定查询需求。
    if parsed.requested_fields:
        filtered = {key: value for key, value in personal_data.items() if key in parsed.requested_fields or key in {"user_id", "name"}}
    else:
        filtered = personal_data
    return {"structured_data": filtered}
