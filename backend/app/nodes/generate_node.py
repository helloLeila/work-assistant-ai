"""答案生成节点。"""

from __future__ import annotations

import json
from typing import Any

from app.chains.response_chain import stream_final_answer


FIXED_IDENTITY_KEYWORDS = (
    "你是谁",
    "你叫什么",
    "你能做什么",
    "你会什么",
    "怎么用",
    "帮助",
)


def _format_context_block(data: object) -> str:
    """把上下文对象转换成更适合模型阅读的文本。"""
    if isinstance(data, str):
        return data
    if isinstance(data, (dict, list)):
        return json.dumps(data, ensure_ascii=False, indent=2)
    return str(data)


async def _push_answer(streamer, answer: str) -> None:
    """逐字推送答案，复用现有 token 协议。"""
    for character in answer:
        await streamer.push_token(character)


def _fixed_chitchat_answer(query: str, intent: str) -> str | None:
    """固定高频问答模板，避免身份/帮助类问题进入 LLM。"""
    if intent != "chitchat":
        return None
    normalized = query.strip().lower()
    if not normalized:
        return None
    if any(keyword in normalized for keyword in FIXED_IDENTITY_KEYWORDS):
        return (
            "我是企业智能办公助手，可以帮你快速查询公司制度、薪酬、个人信息和剩余年假，"
            "也可以处理商旅下单，并协助生成几百字的作文、经验、总结或润色内容。"
        )
    if normalized in {"你好", "您好", "嗨", "hi", "hello"}:
        return "你好，我是企业智能办公助手。你可以直接问我制度、薪酬、年假、个人信息、商旅下单，也可以让我帮你写材料。"
    if normalized in {"谢谢", "辛苦了"}:
        return "不客气，随时叫我。"
    if normalized in {"再见", "拜拜"}:
        return "再见，有需要再来找我。"
    return None


def _format_value(value: Any, suffix: str = "") -> str:
    if value is None or value == "":
        return "暂无"
    if isinstance(value, (int, float)) and suffix:
        return f"{value:g}{suffix}"
    return str(value)


def _structured_direct_answer(intent: str, structured_data: dict[str, Any], travel_info: dict[str, Any]) -> str | None:
    """结构化业务结果模板直出，避免年假/薪酬/商旅再走最终 LLM。"""
    if not structured_data and not travel_info:
        return None

    if "message" in structured_data:
        return str(structured_data["message"])

    if intent == "personal":
        name = str(structured_data.get("name") or "你")
        parts: list[str] = []
        if "annual_leave" in structured_data:
            parts.append(f"剩余年假 {_format_value(structured_data.get('annual_leave'), ' 天')}")
        if "contract_end" in structured_data:
            parts.append(f"合同到期日 {_format_value(structured_data.get('contract_end'))}")
        if "department" in structured_data:
            parts.append(f"所属部门 {_format_value(structured_data.get('department'))}")
        if "phone" in structured_data:
            parts.append(f"手机号 {_format_value(structured_data.get('phone'))}")
        if "id_card" in structured_data:
            parts.append(f"身份证号 {_format_value(structured_data.get('id_card'))}")
        if not parts:
            return None
        return f"{name}，" + "，".join(parts) + "。"

    if intent == "salary":
        month = structured_data.get("payroll_month")
        prefix = f"你最近一期（{month}）的薪酬信息：" if month else "你最近一期的薪酬信息："
        fields = [
            ("总包", "total_package", " 元"),
            ("基本工资", "base_salary", " 元"),
            ("奖金", "bonus", " 元"),
            ("津贴", "allowance", " 元"),
            ("个税", "tax", " 元"),
            ("社保", "social_security", " 元"),
        ]
        details = [
            f"{label} {_format_value(structured_data.get(key), suffix)}"
            for label, key, suffix in fields
            if key in structured_data
        ]
        if not details:
            return None
        return prefix + "，".join(details) + "。"

    if intent == "travel":
        order = structured_data.get("travel_order") if structured_data else None
        if isinstance(order, dict):
            summary = order.get("itinerary_summary") or ""
            order_id = order.get("order_id") or ""
            status = order.get("status") or ""
            reference = order.get("booking_reference")
            answer = f"已为你提交商旅订单{f' {order_id}' if order_id else ''}"
            if status:
                answer += f"，状态：{status}"
            if summary:
                answer += f"。行程：{summary}"
            if reference:
                answer += f"。预订参考号：{reference}"
            return answer + "。"
    return None


async def generate_node(state: dict, runtime) -> dict:
    """整合上下文并生成最终回答。"""
    streamer = runtime.context.streamer

    if state.get("deny_message"):
        answer = state["deny_message"]
        await _push_answer(streamer, answer)
        return {"final_answer": answer}

    if state.get("intent") == "clarify":
        candidates = state.get("candidate_intents", [])
        answer = "我需要进一步确认你的需求。你是想查询" + "、".join(candidates or ["知识库", "薪酬", "个人信息", "商旅"]) + "吗？"
        await _push_answer(streamer, answer)
        return {"final_answer": answer}

    fixed_answer = _fixed_chitchat_answer(state.get("query", ""), state.get("intent", ""))
    if fixed_answer is not None:
        await _push_answer(streamer, fixed_answer)
        return {"final_answer": fixed_answer}

    structured_answer = _structured_direct_answer(
        state.get("intent", ""),
        state.get("structured_data") or {},
        state.get("travel_info") or {},
    )
    if structured_answer is not None:
        await streamer.push_progress(step="generate", detail="已按权限规则整理结构化结果")
        await _push_answer(streamer, structured_answer)
        return {"final_answer": structured_answer}

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
        # 写作类长输出由 planner_node 提前规划，generate_node 把大纲透传给 stream_final_answer。
        # 字段为空字符串/缺失时，stream_final_answer 走无大纲分支。
        outline=state.get("outline", ""),
    )
    return {"final_answer": final_answer}
