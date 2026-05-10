"""回答生成链。"""

from __future__ import annotations

import asyncio
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


async def stream_final_answer(
    *,
    query: str,
    intent: str,
    context: str,
    sources: list[dict[str, object]],
    streamer,
) -> str:
    """生成最终回答，并按 token 流式输出。"""
    # 业务问答保留 extended thinking；普通写作/闲聊走快速生成，避免首 token 前长时间等待。
    llm = get_chat_model(
        temperature=0.2,
        streaming=True,
        tags=["final_response"],
        enable_thinking=should_enable_extended_thinking(intent),
    )

    if llm is not None:
        # 格式子句按 intent 动态切换；放在 system 末尾以利用 LLM 的 recency bias。
        style_clause = format_style_clause(intent)
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
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
                    f"{style_clause}",
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
