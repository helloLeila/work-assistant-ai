"""办公助手 LangGraph 编排。"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from app.core.security import CurrentUser
from app.models.domain import GraphBlueprint
from app.nodes.auth_check_node import auth_check_node, route_after_auth
from app.nodes.generate_node import generate_node
from app.nodes.grader_node import grader_node, route_after_grade
from app.nodes.hallucination_check_node import hallucination_check_node, route_after_hallucination_check
from app.nodes.intent_router_node import intent_router_node, route_by_intent
from app.nodes.knowledge_rag_node import knowledge_rag_node
from app.nodes.personal_info_node import personal_info_node
from app.nodes.salary_query_node import salary_query_node
from app.nodes.travel_booking_node import travel_booking_node
from app.nodes.web_search_node import web_search_node


class GraphState(TypedDict, total=False):
    """整个对话图共享状态。"""

    session_id: str
    query: str
    current_user: CurrentUser
    intent: str
    confidence: float
    candidate_intents: list[str]
    routing_reason: str
    target_user_id: str
    permission_allowed: bool
    deny_message: str
    retrieved_docs: list[dict[str, Any]]
    draft_answer: str
    structured_data: dict[str, Any]
    travel_info: dict[str, Any]
    final_answer: str
    sources: list[dict[str, Any]]
    retry_count: int
    relevant: bool
    retrieval_score: float
    grounded: bool


@dataclass
class GraphRuntimeContext:
    """运行时上下文。"""

    current_user: CurrentUser
    streamer: Any


async def _wrap_generate(state: GraphState, runtime: Runtime[GraphRuntimeContext]) -> Any:
    # generate_node 是异步节点。这里单独包一层，
    # 是为了让编译后的图在运行时稳定处理 await 逻辑。
    return await generate_node(state, runtime)


@lru_cache
def get_office_assistant_graph():
    """编译并缓存 LangGraph 实例。"""
    builder = StateGraph(GraphState, context_schema=GraphRuntimeContext)
    # 先注册节点，再声明边。
    # 这样读代码时能先看到“有哪些步骤”，再看“步骤怎么流转”。
    builder.add_node("intent_router_node", intent_router_node)
    builder.add_node("knowledge_rag_node", knowledge_rag_node)
    builder.add_node("grader_node", grader_node)
    builder.add_node("web_search_node", web_search_node)
    builder.add_node("auth_check_node", auth_check_node)
    builder.add_node("salary_query_node", salary_query_node)
    builder.add_node("personal_info_node", personal_info_node)
    builder.add_node("travel_booking_node", travel_booking_node)
    builder.add_node("generate_node", _wrap_generate)
    builder.add_node("hallucination_check_node", hallucination_check_node)

    builder.add_edge(START, "intent_router_node")
    # 第一层路由先按意图拆业务主路径。
    builder.add_conditional_edges(
        "intent_router_node",
        route_by_intent,
        {
            "knowledge_rag_node": "knowledge_rag_node",
            "auth_check_node": "auth_check_node",
            "travel_booking_node": "travel_booking_node",
            "generate_node": "generate_node",
        },
    )
    # 第二层路由专门处理敏感数据的权限判断。
    builder.add_conditional_edges(
        "auth_check_node",
        route_after_auth,
        {
            "salary_query_node": "salary_query_node",
            "personal_info_node": "personal_info_node",
            "generate_node": "generate_node",
        },
    )
    builder.add_edge("knowledge_rag_node", "grader_node")
    # 知识库命中的内容先过相关性判断，不够再走补充路径。
    builder.add_conditional_edges(
        "grader_node",
        route_after_grade,
        {
            "generate_node": "generate_node",
            "web_search_node": "web_search_node",
        },
    )
    builder.add_edge("web_search_node", "generate_node")
    builder.add_edge("salary_query_node", "generate_node")
    builder.add_edge("personal_info_node", "generate_node")
    builder.add_edge("travel_booking_node", "generate_node")
    builder.add_edge("generate_node", "hallucination_check_node")
    # 最终回答生成后再做一次可信度检查，必要时允许重试。
    builder.add_conditional_edges(
        "hallucination_check_node",
        route_after_hallucination_check,
        {
            "generate_node": "generate_node",
            END: END,
        },
    )
    return builder.compile(checkpointer=InMemorySaver(), name="office_assistant_graph")


def build_graph_blueprint() -> GraphBlueprint:
    """返回图结构概要。"""
    return GraphBlueprint(
        entrypoint="intent_router_node",
        nodes=[
            "intent_router_node",
            "knowledge_rag_node",
            "grader_node",
            "web_search_node",
            "auth_check_node",
            "salary_query_node",
            "personal_info_node",
            "travel_booking_node",
            "generate_node",
            "hallucination_check_node",
        ],
        edges={
            "intent_router_node": ["knowledge_rag_node", "auth_check_node", "travel_booking_node", "generate_node"],
            "knowledge_rag_node": ["grader_node"],
            "grader_node": ["generate_node", "web_search_node"],
            "auth_check_node": ["salary_query_node", "personal_info_node", "generate_node"],
            "salary_query_node": ["generate_node"],
            "personal_info_node": ["generate_node"],
            "travel_booking_node": ["generate_node"],
            "generate_node": ["hallucination_check_node"],
            "hallucination_check_node": ["generate_node", "__end__"],
        },
        features=["routing", "checkpoint", "conditional_edges", "retry_guard", "streaming"],
        checkpoint="InMemorySaver",
    )
