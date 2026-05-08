"""回答可信度检查节点。"""

from __future__ import annotations

from app.core.config import get_settings


async def hallucination_check_node(state: dict) -> dict:
    """检查回答是否有足够依据。"""
    intent = state.get("intent")
    final_answer = state.get("final_answer", "")
    sources = state.get("sources", [])
    retry_count = int(state.get("retry_count", 0))

    grounded = True
    if intent == "knowledge":
        grounded = bool(sources) and bool(final_answer.strip())
    if intent in {"salary", "personal", "travel"}:
        grounded = bool(state.get("structured_data"))

    updates = {"grounded": grounded}
    if not grounded:
        updates["retry_count"] = retry_count + 1
        if updates["retry_count"] >= get_settings().max_retry_count:
            updates["final_answer"] = "我暂时无法在现有上下文中稳定生成可信答案，请稍后重试或补充更多信息。"
            updates["grounded"] = True
    return updates


def route_after_hallucination_check(state: dict) -> str:
    """判断是否结束。"""
    if state.get("grounded"):
        return "__end__"
    return "generate_node"
