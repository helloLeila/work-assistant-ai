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
from app.nodes.planner_node import planner_node
from app.nodes.salary_query_node import salary_query_node
from app.nodes.travel_booking_node import travel_booking_node
from app.nodes.web_search_node import web_search_node


class GraphState(TypedDict, total=False):
    """整个对话图共享状态。"""

    session_id: str
    query: str
    current_user: CurrentUser
    client_ip: str | None
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
    artifacts: list[dict[str, Any]]
    travel_info: dict[str, Any]
    # 写作类长请求由 planner_node 产出的段落大纲，generate_node 会读这个字段决定是否分段展开。
    # 字段为空字符串或缺失都视为'无大纲'，generate 走原逻辑。
    outline: str
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


def _status_label_for_state(default_label: str, step: str, state: GraphState) -> str:
    """根据当前 intent 调整步骤文案，避免结构化业务都显示“生成正文”。"""
    if step != "generate":
        return default_label
    intent = state.get("intent")
    labels = {
        "salary": "整理薪酬结果",
        "personal": "整理个人信息",
        "travel": "确认商旅订单",
        "knowledge": "综合制度内容",
        "chitchat": "撰写正文",
    }
    return labels.get(intent, default_label)


def _with_status(
    node_fn,
    *,
    step: str,
    label: str,
    takes_runtime: bool = False,
):
    """给节点加一层状态推送外壳。

    每个节点入口 push status=running、出口 push status=done，前端据此实时显示
    "理解问题中…""检索知识库中…""组织答案中…"等步骤，不用干等 16 秒秒表。

    takes_runtime：传给内部节点函数时是否需要 runtime 参数（目前只有 generate_node 需要，
    因为它要用 runtime.context.streamer 去流 token）。
    """

    async def wrapped(state: GraphState, runtime: Runtime[GraphRuntimeContext]):
        streamer = getattr(runtime.context, "streamer", None)
        status_label = _status_label_for_state(label, step, state)
        if streamer is not None:
            await streamer.push_status(step=step, label=status_label, state="running")
        try:
            if takes_runtime:
                result = await node_fn(state, runtime)
            else:
                result = await node_fn(state)
            if streamer is not None and step == "intent" and isinstance(result, dict):
                reason = str(result.get("routing_reason") or "")
                intent = str(result.get("intent") or "")
                if reason:
                    await streamer.push_progress(step=step, detail=reason)
                if intent == "chitchat":
                    await streamer.push_trace(step="route", label="规划回答方式", detail="按你的主题和字数要求组织回答")
            return result
        finally:
            # 无论节点抛异常与否都发 done，避免前端 spinner 卡死。
            # 异常本身会由上层 run_streaming_chat 的 try/except 捕获并 push_error。
            if streamer is not None:
                await streamer.push_status(step=step, label=status_label, state="done")

    return wrapped


@lru_cache
def get_office_assistant_graph():
    """编译并缓存 LangGraph 实例。"""
    builder = StateGraph(GraphState, context_schema=GraphRuntimeContext)
    # 先注册节点，再声明边。
    # 这样读代码时能先看到“有哪些步骤”，再看“步骤怎么流转”。
    # 每个节点都经 _with_status 包一层，把"现在在做什么"实时同步给前端气泡。
    builder.add_node(
        "intent_router_node",
        _with_status(intent_router_node, step="intent", label="理解需求"),
    )
    builder.add_node(
        "knowledge_rag_node",
        _with_status(knowledge_rag_node, step="retrieve", label="检索知识库"),
    )
    builder.add_node(
        "grader_node",
        _with_status(grader_node, step="grade", label="筛选相关内容"),
    )
    builder.add_node(
        "web_search_node",
        _with_status(web_search_node, step="web_search", label="联网补充检索"),
    )
    builder.add_node(
        "auth_check_node",
        _with_status(auth_check_node, step="auth", label="校验访问权限"),
    )
    builder.add_node(
        "salary_query_node",
        _with_status(salary_query_node, step="salary", label="查询薪酬信息"),
    )
    builder.add_node(
        "personal_info_node",
        _with_status(personal_info_node, step="profile", label="查询个人信息"),
    )
    builder.add_node(
        "travel_booking_node",
        _with_status(travel_booking_node, step="travel", label="处理差旅请求"),
    )
    # planner_node 仅对 chitchat + 长字数请求实质规划，其余请求是 pass-through，
    # 所以放心地把 chitchat 路径都串过它，不会增加无关请求的延迟。
    builder.add_node(
        "planner_node",
        _with_status(planner_node, step="plan", label="规划回答结构", takes_runtime=True),
    )
    # generate_node 需要 runtime（拿 streamer 去流 token），单独走 takes_runtime=True。
    builder.add_node(
        "generate_node",
        _with_status(generate_node, step="generate", label="生成正文", takes_runtime=True),
    )
    # hallucination_check_node 通常毫秒级，不 push status 避免多余噪声。
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
            "web_search_node": "web_search_node",
            # chitchat / 写作类现在统一先过 planner_node 做长输出规划；
            # 短查询/无字数要求时 planner 是 pass-through，几乎零开销。
            "planner_node": "planner_node",
        },
    )
    builder.add_edge("planner_node", "generate_node")
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
            "planner_node",
            "generate_node",
            "hallucination_check_node",
        ],
        edges={
            "intent_router_node": [
                "knowledge_rag_node",
                "auth_check_node",
                "travel_booking_node",
                "web_search_node",
                "planner_node",
            ],
            "knowledge_rag_node": ["grader_node"],
            "grader_node": ["generate_node", "web_search_node"],
            "auth_check_node": ["salary_query_node", "personal_info_node", "generate_node"],
            "salary_query_node": ["generate_node"],
            "personal_info_node": ["generate_node"],
            "travel_booking_node": ["generate_node"],
            "planner_node": ["generate_node"],
            "generate_node": ["hallucination_check_node"],
            "hallucination_check_node": ["generate_node", "__end__"],
        },
        features=["routing", "checkpoint", "conditional_edges", "retry_guard", "streaming"],
        checkpoint="InMemorySaver",
    )
