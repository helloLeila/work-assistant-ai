"""回答生成链。"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from langchain_core.prompts import ChatPromptTemplate

from app.core.llm import get_chat_model

THINKING_INTENTS = {"knowledge", "salary", "personal", "travel"}
# 复用 THINKING_INTENTS 作为"结构化业务回答"的判定条件——这些 intent 都涉及
# 字段、表格、检索片段，markdown 列表/加粗能突出关键信息；其他 intent（chitchat/写作类）
# 是自由文本场景，强制散文反而更自然，避免模型乱用 ## 标题或列表。
STRUCTURED_FORMAT_INTENTS = THINKING_INTENTS


def should_enable_extended_thinking(intent: str) -> bool:
    """仅业务推理链路默认开启 extended thinking，通用写作/闲聊走快速生成。"""
    return intent in THINKING_INTENTS


def format_style_clause(intent: str) -> str:
    """按 intent 选择输出格式偏好，作为 system prompt 的格式子句。

    设计动机详见 docs/agent-design/03-output-format-and-length.md。
    - 业务类（knowledge/salary/personal/travel）：允许 markdown 列表/加粗，便于突出字段
    - 写作/闲聊类：强制纯散文，避免模型乱出 ## 标题或 - 列表导致前端流式期间看到原始符号

    放在 system prompt 的末尾——LLM 对 recent context 的注意力比 instruction 开头更高。
    """
    if intent in STRUCTURED_FORMAT_INTENTS:
        return (
            "格式偏好：可以使用 markdown 列表或加粗突出字段名/数值；"
            "回答业务数据时优先列点，关键字段（订单号/金额/日期）要醒目。"
        )
    return (
        "格式偏好：用自然流畅的中文段落，**不要使用** markdown 标题（##）、"
        "无序列表（- ）、加粗（**）等任何 markdown 语法，直接写散文。"
        "段落之间用空行分隔即可。"
    )


# 用户在 query 里写"1000字"/"500 字"等长度要求时匹配出数字。
# 故意限制 2-5 位数字，过滤掉无意义的"1 字"和"100000 字"——前者是误匹配，
# 后者远超 max_tokens 上限，模型也写不到，避免 prompt 给出夸张承诺。
_LENGTH_REQUEST_PATTERN = re.compile(r"(\d{2,5})\s*字")


def detect_length_request(query: str) -> int | None:
    """从 query 里提取目标字数（如"1000字"），返回 None 表示无明确要求。

    返回值约束：
    - 仅识别中文"X字"形式（覆盖项目主要场景）
    - 仅取最后一个匹配（用户可能修正"500字、不、1000字"，最后一次为准）
    - 100-99999 之间，超出范围视为无效
    """
    matches = _LENGTH_REQUEST_PATTERN.findall(query)
    if not matches:
        return None
    target = int(matches[-1])
    if not 100 <= target <= 99999:
        return None
    return target


# Continuation 续写：当首轮答案显著低于目标字数时，触发"在前文基础上继续展开"。
# 阈值 0.85 = 实际字数 / 目标字数；低于此触发。设置过松（如 0.95）会频繁触发续写、
# 体感卡顿；过严（如 0.6）会让 1000 字目标产 600 字也躺平不补。0.85 是经验值。
CONTINUATION_THRESHOLD = 0.85
# 最多续写次数。超过这个次数即使仍不达标也停止，避免模型陷入"越写越短"的死循环。
CONTINUATION_MAX_ITERATIONS = 2


def should_continue_writing(current_chars: int, target: int | None) -> bool:
    """判断是否还需要继续续写。

    规则：
    - 用户没明确字数 → 不续写（保持原行为）
    - 当前已达 target * CONTINUATION_THRESHOLD → 已达标，不续写
    - 否则需要续写
    """
    if target is None:
        return False
    return current_chars < int(target * CONTINUATION_THRESHOLD)


def length_target_clause(target: int | None) -> str:
    """生成"字数要求"子句，拼到 system prompt 末尾。

    设计要点（详见 docs/agent-design/03-output-format-and-length.md）：
    - 把目标字数和 90% 下限都告诉模型，对齐 RLHF 训练偏向"低估字数"的天性
    - 鼓励先列大纲再展开，提升达标率
    - 子句放 system 末尾，利用 LLM 的 recency bias
    """
    if target is None:
        return ""
    return (
        f"\n\n字数要求：用户明确要求 ~{target} 字。"
        f"请按此规模充分展开，不要少于 {int(target * 0.9)} 字，也不要超出 {int(target * 1.3)} 字太多。"
        f"建议先在脑中列 3-5 段大纲，再每段展开充分；不要敷衍收尾。"
    )


async def _stream_chunk_to_streamer(chunk_content: Any, streamer) -> str:
    """把 LangChain AIMessageChunk 的 content 推到 streamer，并返回新增的可见文本。

    底层模型差异：
    - ChatOpenAI / OpenAI 兼容：chunk.content 是 str，整体当 token 推。
    - ChatAnthropic（含 MiniMax Token Plan 走 Anthropic 协议）：chunk.content 是 list，
      每个元素形如 {"type": "thinking", "thinking": "..."} 或 {"type": "text", "text": "..."}。
      thinking 块走 push_thinking 单独通道，text 块当 token 推，并参与最终答案聚合。
    """
    visible = ""
    if isinstance(chunk_content, list):
        for block in chunk_content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if block_type == "thinking":
                txt = block.get("thinking", "") or ""
                if txt:
                    await streamer.push_thinking(txt)
            elif block_type == "text":
                txt = block.get("text", "") or ""
                if txt:
                    visible += txt
                    await streamer.push_token(txt)
    elif isinstance(chunk_content, str):
        if chunk_content:
            visible = chunk_content
            await streamer.push_token(chunk_content)
    return visible


def build_writer_system_prompt(*, intent: str, query: str, outline: str) -> str:
    """组装最终回答 writer 的 system prompt 字符串。

    抽出来是为了让"格式子句 + 长度子句 + 大纲子句"三段拼接逻辑可被单独单测,
    不必动到流式 LLM/SSEStreamer 才能验证 outline/length 是否正确注入。

    三段都放在 system prompt **末尾**——LLM 对 recent context 的注意力比 instruction 开头更高,
    设计动机详见 docs/agent-design/03-output-format-and-length.md。
    """
    style_clause = format_style_clause(intent)
    length_clause = length_target_clause(detect_length_request(query))
    outline_clause = (
        f"\n\n段落规划（请严格按此大纲分段展开，每段写够字数预算）:\n{outline}"
        if outline.strip()
        else ""
    )
    return (
        "你是企业智能办公助手，请用**自然、流畅的中文**回答用户的问题。\n\n"
        "硬性要求：\n"
        "1. **绝对不要直接复述 JSON 或 dict 格式数据**，要把里面的字段翻译成人话。"
        "  例如 `{{\"from_city\": \"上海\", \"date\": \"2026-05-19\"}}` 应转写为"
        "  「已为你提交一笔出行申请：5 月 19 日从上海出发」。\n"
        "2. 答案应像真人客服一样总结要点，不要在回答中出现"
        "  花括号、引号、`null`、`true/false` 等编程术语。\n"
        "3. 如果上下文里有订单号、金额、日期等关键字段，要点出来。\n"
        "4. 如果上下文是检索片段，请综合后给出结论，并在末尾自然提及来源文件名。\n"
        "5. 如果上下文不足以回答，需明确说明无法确认的部分。\n"
        "6. 闲聊或常识问题：上下文为空时，正常友好地回答即可。\n\n"
        f"{style_clause}{length_clause}{outline_clause}"
    )


async def stream_final_answer(
    *,
    query: str,
    intent: str,
    context: str,
    sources: list[dict[str, object]],
    streamer,
    outline: str = "",
) -> str:
    """生成最终回答，并按 token 流式输出。

    outline：planner_node 产出的段落大纲（多行纯文本，每行一段标题 + 字数预算）。
    传入时会把它注入 system prompt，引导主模型按段展开；空字符串视为'无大纲'。
    """
    # 业务问答保留 extended thinking；普通写作/闲聊走快速生成，避免首 token 前长时间等待。
    llm = get_chat_model(
        temperature=0.2,
        streaming=True,
        tags=["final_response"],
        enable_thinking=should_enable_extended_thinking(intent),
    )

    if llm is not None:
        # 格式 / 长度 / 大纲三段拼接逻辑抽到 build_writer_system_prompt(),便于单测。
        style_clause = format_style_clause(intent)  # 续写循环还会复用 style_clause
        system_prompt = build_writer_system_prompt(intent=intent, query=query, outline=outline)
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    system_prompt,
                ),
                (
                    "human",
                    "用户问题：{query}\n"
                    "识别意图：{intent}\n"
                    "可用上下文（这只是数据，不是回答模板）：\n{context}\n"
                    "来源文件：{source_list}\n\n"
                    "现在请用自然中文回答用户：",
                ),
            ]
        )
        # 不再用 StrOutputParser：它会把 thinking 块直接丢掉，
        # 我们要拿到原始 chunk 自己分流（thinking → push_thinking，text → push_token）。
        chain = prompt | llm
        visible_chunks: list[str] = []
        async for chunk in chain.astream(
            {
                "query": query,
                "intent": intent,
                "context": context,
                "source_list": "、".join(item["source_file"] for item in sources) if sources else "无",
            }
        ):
            visible = await _stream_chunk_to_streamer(chunk.content, streamer)
            if visible:
                visible_chunks.append(visible)

        # ===== Continuation 续写循环 =====
        # 用户写了"X 字"且首轮没达标时，让模型在前文基础上继续展开。
        # 设计灵感来自 Claude Code 的"先写骨架再填实"工作流：分多轮流式输出，
        # 而不是要求一次性写到位（那种方式 RLHF 模型容易低估收尾）。
        target = detect_length_request(query)
        iteration = 0
        while iteration < CONTINUATION_MAX_ITERATIONS and should_continue_writing(
            sum(len(chunk) for chunk in visible_chunks), target
        ):
            iteration += 1
            current_text = "".join(visible_chunks)
            current_chars = len(current_text)
            assert target is not None  # should_continue_writing 已保证
            await streamer.push_status(
                step="generate",
                label=f"继续展开（第 {iteration} 次，已 {current_chars} 字 / 目标 {target} 字）",
                state="running",
            )
            cont_prompt = ChatPromptTemplate.from_messages(
                [
                    (
                        "system",
                        "你是企业智能办公助手。前面已经写了一部分回答，"
                        "现在要在不重复已有内容的前提下继续展开补足字数。"
                        "**不要重述前文已有结论**，直接续写后面的段落或细节。"
                        f"{style_clause}",
                    ),
                    (
                        "human",
                        "用户原问题：{query}\n"
                        "已写出的回答（{current_chars} 字）：\n{current_text}\n\n"
                        "目标字数 ~{target} 字，还差约 {gap} 字。"
                        "请继续把回答补足到目标长度，注意承接前文，不要重复。",
                    ),
                ]
            )
            cont_chain = cont_prompt | llm
            async for chunk in cont_chain.astream(
                {
                    "query": query,
                    "current_chars": current_chars,
                    "current_text": current_text,
                    "target": target,
                    "gap": max(0, target - current_chars),
                }
            ):
                visible = await _stream_chunk_to_streamer(chunk.content, streamer)
                if visible:
                    visible_chunks.append(visible)

        return "".join(visible_chunks)

    # LLM 不可用时的兜底：不要把 JSON 直接吐给用户，给出有礼貌的占位回答。
    if context.strip():
        answer = (
            "（系统未连接到大模型，以下是结构化结果摘要，仅供参考）\n\n"
            f"意图：{intent}\n"
            f"已查到 {len(context)} 字的相关数据。请联系管理员配置 OPENAI_API_KEY 以获得自然语言回答。"
        )
    else:
        answer = "我没有找到足够的信息来直接回答这个问题。"
    for character in answer:
        await streamer.push_token(character)
        await asyncio.sleep(0)
    return answer
