"""权限检查节点。langgraph"""

from __future__ import annotations

from app.services.payroll_service import get_payroll_service
from app.services.personal_info_service import get_personal_info_service


async def auth_check_node(state: dict) -> dict:
    """在敏感业务节点前做权限判断。"""
    intent = state["intent"]
    current_user = state["current_user"]
    query = state["query"]

    if intent == "salary":
        service = get_payroll_service()
        target_user_id = service.resolve_target_user_id(query, current_user)
        decision = service.authorize(current_user, target_user_id)
    else:
        service = get_personal_info_service()
        target_user_id = service.resolve_target_user_id(query, current_user)
        decision = service.authorize(current_user, target_user_id)

    return {
        "target_user_id": decision.target_user_id,
        "permission_allowed": decision.allowed,
        "deny_message": decision.message,
    }


def route_after_auth(state: dict) -> str:
    """根据权限结果决定下一节点。"""
    if not state.get("permission_allowed", False):
        return "generate_node"
    return "salary_query_node" if state["intent"] == "salary" else "personal_info_node"
