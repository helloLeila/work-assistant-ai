"""意图路由节点。"""

from __future__ import annotations

from app.chains.intent_chain import classify_intent


async def intent_router_node(state: dict) -> dict:
    """识别用户意图。"""
    result = await classify_intent(state["query"])
    return {
        "intent": result.intent,
        "confidence": result.confidence,
        "candidate_intents": result.candidate_intents,
        "routing_reason": result.reason,
    }


def route_by_intent(state: dict) -> str:
    """根据意图决定下一节点。"""
    mapping = {
        "knowledge": "knowledge_rag_node",
        "salary": "auth_check_node",
        "personal": "auth_check_node",
        "travel": "travel_booking_node",
        "web_research_write": "web_search_node",
        "direct_write": "planner_node",
        "chitchat": "planner_node",
        "clarify": "planner_node",
    }
    return mapping.get(state.get("intent", "clarify"), "planner_node")
