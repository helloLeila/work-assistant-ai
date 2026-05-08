"""答案生成节点。"""

from __future__ import annotations

import json

from app.chains.response_chain import stream_final_answer


def _format_context_block(data: object) -> str:
    """把上下文对象转换成更适合模型阅读的文本。"""
    if isinstance(data, str):
        return data
    if isinstance(data, (dict, list)):
        return json.dumps(data, ensure_ascii=False, indent=2)
    return str(data)


async def generate_node(state: dict, runtime) -> dict:
    """整合上下文并生成最终回答。"""
    if state.get("deny_message"):
        answer = state["deny_message"]
        streamer = runtime.context.streamer
        for character in answer:
            await streamer.push_token(character)
        return {"final_answer": answer}

    if state.get("intent") == "clarify":
        candidates = state.get("candidate_intents", [])
        answer = "我需要进一步确认你的需求。你是想查询" + "、".join(candidates or ["知识库", "薪酬", "个人信息", "商旅"]) + "吗？"
        streamer = runtime.context.streamer
        for character in answer:
            await streamer.push_token(character)
        return {"final_answer": answer}

    context_parts: list[str] = []
    if state.get("draft_answer"):
        context_parts.append(_format_context_block(state["draft_answer"]))
    if state.get("structured_data"):
        context_parts.append(_format_context_block(state["structured_data"]))
    if state.get("travel_info"):
        context_parts.append(_format_context_block(state["travel_info"]))
    if state.get("sources"):
        context_parts.append(
            "\n".join(f"{item['source_file']} 第{item['page_num']}段：{item['snippet']}" for item in state["sources"])
        )

    final_answer = await stream_final_answer(
        query=state["query"],
        intent=state["intent"],
        context="\n\n".join(part for part in context_parts if part),
        sources=state.get("sources", []),
        streamer=runtime.context.streamer,
    )
    return {"final_answer": final_answer}
