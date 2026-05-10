"""写作类规划节点。

定位：写作/闲聊场景下，在 generate_node 之前先跑一遍 planner_chain，
把段落大纲落到 GraphState["outline"]，让 generate_node 按大纲分段展开。

仅对满足 should_run_planner() 的请求实质跑规划；其他请求直接 pass-through，
返回空 dict 不污染 state。这样图编排可以无脑把所有 chitchat 路径都连过 planner_node。
"""

from __future__ import annotations

from app.chains.planner_chain import plan_writing_outline, should_run_planner
from app.chains.response_chain import detect_length_request


async def planner_node(state: dict, runtime) -> dict:
    """为写作类长请求规划大纲。

    需要 runtime 是为了拿到 streamer 把大纲流给前端——
    在主模型还没开始吐 token 的几秒里，先让用户看到"已规划 3 段大纲..."
    比死秒表/通用"组织答案中"更踏实。大纲走 thinking 通道，前端在折叠块里渲染。
    """
    query: str = state.get("query", "")
    intent: str = state.get("intent", "")
    target_chars = detect_length_request(query)

    if not should_run_planner(intent=intent, target_chars=target_chars):
        # 不需要规划——返回空 dict，让后续 generate_node 走原逻辑。
        # 注意：返回 {} 比返回 {"outline": ""} 更好，前者不会触发 GraphState 字段写入，
        # 后端调试日志更干净。
        return {}

    outline = await plan_writing_outline(query=query, target_chars=target_chars or 0)
    if not outline:
        # planner 调用失败（LLM 不可用 / 网络故障）也不阻塞主流程，
        # generate_node 走无大纲分支即可。
        return {}

    # 把大纲先流给前端做即时反馈。失败不阻塞主流程。
    streamer = getattr(runtime.context, "streamer", None) if runtime is not None else None
    if streamer is not None:
        try:
            await streamer.push_thinking(f"📝 已规划写作大纲：\n{outline}\n")
        except Exception:
            # 流推送故障绝不影响主链路；状态/done 由 _with_status 兜底。
            pass

    return {"outline": outline}
