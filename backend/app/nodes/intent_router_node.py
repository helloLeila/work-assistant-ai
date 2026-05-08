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
        "chitchat": "generate_node",
        "clarify": "generate_node",
    }
    return mapping.get(state.get("intent", "clarify"), "generate_node")
