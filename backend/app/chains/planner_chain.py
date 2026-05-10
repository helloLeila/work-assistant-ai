"""写作类长输出的大纲规划链。

灵感来自 Claude Code / 主流 Agent 的"plan-then-write"工作流：
长输出请求(>= 500 字)先用一个**轻量**调用产出大纲，再让主模型按大纲展开。

为什么有用：
- RLHF 模型一次性写到 1000 字会"前重后轻"——开头详细、结尾敷衍
- 给出明确的段落预算后，模型按段写每段都能写够，整体更均衡
- 大纲本身可以流给前端做 UI 展示("📝 已规划 3 段大纲...")

详见 docs/agent-design/03-output-format-and-length.md。
"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

from app.core.llm import get_chat_model

# 触发 planner 的最小字数门槛。低于此值不规划——直接让 generate 一气呵成更快，
# 大纲反而是开销。500 字大致是"两段以上正经回答"的边界。
PLANNER_MIN_TARGET_CHARS = 500


def should_run_planner(*, intent: str, target_chars: int | None) -> bool:
    """判断是否要跑 planner 规划。

    规则：
    - 必须有明确字数要求（detect_length_request 返回值）
    - 字数要求 >= PLANNER_MIN_TARGET_CHARS
    - 仅对 chitchat（写作类、自由问答）启用——业务类有结构化数据，无需大纲
    """
    if intent != "chitchat":
        return False
    if target_chars is None or target_chars < PLANNER_MIN_TARGET_CHARS:
        return False
    return True


async def plan_writing_outline(query: str, target_chars: int) -> str:
    """为长输出请求生成段落大纲。

    返回值：纯文本大纲字符串（多行，每行一段标题 + 字数预算）。
    设计权衡：
    - 选用纯文本而不是 JSON——LLM 写大纲不需要结构化解析，少跑一次 parser
    - 字数预算明确写出（"~300 字"），让主模型生成时按预算分配，对齐 RLHF 低估天性

    LLM 不可用时返回空字符串，调用方应回退到无大纲生成。
    """
    llm = get_chat_model(temperature=0.3, tags=["writing_planner"])
    if llm is None:
        return ""

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "你是中文长文写作助手。给定用户的写作请求和目标字数，"
                "请产出一份**段落大纲**：3-5 段，每段一行，格式为：\n"
                "  第 N 段（~XXX 字）: 段落主题简述\n"
                "硬性要求：\n"
                "1. 各段字数预算之和应接近目标字数\n"
                "2. 大纲本身不超过 200 字，要简洁\n"
                "3. 不要写正文，只列段落主题\n"
                "4. 不要使用 markdown 标题/加粗/列表符号，每段就用'第 N 段'开头",
            ),
            (
                "human",
                "用户请求：{query}\n目标字数：~{target_chars} 字\n\n请输出段落大纲：",
            ),
        ]
    )
    chain = prompt | llm
    result = await chain.ainvoke({"query": query, "target_chars": target_chars})
    # ChatAnthropic 返回 list（thinking + text 混合），ChatOpenAI 返回 str
    content = result.content if hasattr(result, "content") else str(result)
    if isinstance(content, list):
        text_parts = [
            block.get("text", "") for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return "".join(text_parts).strip()
    return str(content).strip()
