"""意图分类链。"""

from __future__ import annotations

import asyncio

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.core.config import get_settings
from app.core.llm import get_utility_chat_model
from app.models.domain import IntentClassification

FEW_SHOTS = """
用户：帮我查一下公司的差旅制度
输出：{"intent":"knowledge","confidence":0.93,"candidate_intents":["knowledge","travel"],"reason":"用户在询问制度文档内容"}

用户：请查我的本月薪酬
输出：{"intent":"salary","confidence":0.95,"candidate_intents":["salary","personal"],"reason":"用户明确提到薪酬"}

用户：帮我看一下剩余年假
输出：{"intent":"personal","confidence":0.92,"candidate_intents":["personal","knowledge"],"reason":"用户在查询个人人事信息"}

用户：下周二订上海到深圳的机票
输出：{"intent":"travel","confidence":0.96,"candidate_intents":["travel","knowledge"],"reason":"用户要办理出行预订"}

用户：2026 年 AI Agent 趋势是什么
输出：{"intent":"web_research_write","confidence":0.94,"candidate_intents":["web_research_write","direct_write"],"reason":"用户询问最新趋势，需要联网素材"}

用户：帮我生成 200 字 agent 总结
输出：{"intent":"direct_write","confidence":0.91,"candidate_intents":["direct_write","web_research_write"],"reason":"用户要求写作，但未明确是否需要外部素材"}
""".strip()


# 第一层快速路径：关键词。详见 docs/agent-design/02-routing-and-model-tiers.md。
# 命中即跳过 LLM 分类，对高频常见问题直接返回意图，延迟 ~0ms。
# chitchat 只保留问候/身份/通用闲聊，写作类拆到 direct_write，联网类拆到 web_research_write。
KEYWORD_RULES: tuple[tuple[str, list[str], list[str]], ...] = (
    ("salary", ["薪酬", "工资", "总包", "奖金", "薪资", "个税", "收入"], ["personal"]),
    ("personal", ["年假", "合同", "身份证", "手机号", "个人信息", "入职", "部门"], ["knowledge"]),
    ("travel", ["机票", "酒店", "出差", "商旅", "预订", "航班", "舱位", "乘客"], ["knowledge"]),
    ("knowledge", ["制度", "报销", "手册", "知识库", "规定", "政策", "流程", "标准", "FAQ"], ["travel"]),
    (
        "web_research_write",
        [
            "今天", "明天", "昨天", "最新", "最近", "2026", "趋势",
            "天气", "新闻", "查一下", "搜一下", "联网", "实时",
        ],
        ["direct_write", "knowledge"],
    ),
    (
        "direct_write",
        [
            "生成", "写", "撰写", "面试", "经验", "介绍", "总结", "润色", "改写",
        ],
        ["web_research_write", "knowledge"],
    ),
    (
        "chitchat",
        [
            "你是谁", "你叫啥","你叫什么", "你好", "您好", "嗨",
            "你能做什么", "你会什么", "怎么用", "帮助",
            "谢谢", "辛苦了", "再见", "拜拜",
            "hi", "hello",
        ],
        ["knowledge"],
    ),
)

# 短查询兜底：≤ SHORT_QUERY_FALLBACK_CHARS 字符且无业务关键词命中时，
# 默认归为 chitchat。对"在吗""嗯""ok""hello?"这类没穷举到的零碎闲聊也能秒过。
# 阈值放宽到 15 字是经验值——业务请求基本都 >15 字（"帮我看看本月薪酬""差旅最多能报多少"）。
SHORT_QUERY_FALLBACK_CHARS = 15
UTILITY_CLASSIFIER_TIMEOUT_SECONDS = 1.5


def _classify_local_datetime_query(query: str) -> IntentClassification | None:
    """今天几号/星期几这类本地时间问题直接走 chitchat。"""
    normalized = query.strip().lower()
    if "今天" not in normalized:
        return None

    date_keywords = ("几号", "日期", "几月几号")
    weekday_keywords = ("星期几", "周几", "礼拜几")
    if not any(keyword in normalized for keyword in (*date_keywords, *weekday_keywords)):
        return None

    return IntentClassification(
        intent="chitchat",
        confidence=0.95,
        candidate_intents=["chitchat", "web_research_write"],
        reason="本地快速路径命中日期/星期问题",
    )


def _classify_by_local_keywords(query: str) -> IntentClassification | None:
    """用本地关键词处理明显意图，避免每轮都先等远端 LLM。"""
    date_result = _classify_local_datetime_query(query)
    if date_result is not None:
        return date_result

    matches: list[tuple[str, list[str], list[str]]] = []
    for intent, keywords, fallbacks in KEYWORD_RULES:
        hit_words = [word for word in keywords if word.lower() in query.lower()]
        if hit_words:
            matches.append((intent, hit_words, fallbacks))

    if not matches:
        return None

    # 多个意图同时命中时交给 LLM 判别，避免"差旅报销制度"这类问题被过早定死。
    top_score = len(matches[0][1])
    if sum(1 for _, hit_words, _ in matches if len(hit_words) == top_score) > 1:
        return None

    intent, hit_words, fallbacks = max(matches, key=lambda item: len(item[1]))
    return IntentClassification(
        intent=intent,
        confidence=0.93,
        candidate_intents=[intent, *fallbacks],
        reason=f"本地快速路径命中关键词：{'、'.join(hit_words)}",
    )


def _short_query_chitchat_fallback(query: str) -> IntentClassification | None:
    """≤ SHORT_QUERY_FALLBACK_CHARS 字的短查询且未命中业务关键词时，默认归为 chitchat。

    业务请求几乎都 >15 字（"帮我看看本月薪酬""差旅报销最多能报多少"），短 query 大概率是
    "在吗""ok""hello?"这种零碎闲聊。这层兜底让所有短文本都走 chitchat fast-path，
    避免主模型为一句问候等 25 秒。
    """
    stripped = query.strip()
    if not stripped or len(stripped) > SHORT_QUERY_FALLBACK_CHARS:
        return None
    return IntentClassification(
        intent="chitchat",
        confidence=0.85,
        candidate_intents=["chitchat", "knowledge"],
        reason=f"本地快速路径：短查询(≤{SHORT_QUERY_FALLBACK_CHARS} 字)默认 chitchat",
    )


async def classify_intent(query: str) -> IntentClassification:
    """执行意图分类。"""
    # 第一层：业务/写作关键词命中
    local_result = _classify_by_local_keywords(query)
    if local_result is not None:
        return local_result

    # 第二层：短查询兜底（"在吗""ok""hello?" 这种没穷举到的零碎闲聊）
    short_fallback = _short_query_chitchat_fallback(query)
    if short_fallback is not None:
        return short_fallback

    parser = PydanticOutputParser(pydantic_object=IntentClassification)
    # 第三层：utility tier 小模型分类（gpt-4o-mini / claude-haiku 等），把延迟从 ~25s 降到 ~1-2s。
    # MiniMax Coding Plan 等只暴露主模型的供应商会自动回退到主模型，至少不会更慢。
    llm = get_utility_chat_model(temperature=0, tags=["intent_router"])

    if llm is not None:
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是企业智能办公助手的意图分类器。请根据用户问题返回 JSON。"
                    "意图只能是 knowledge、salary、personal、travel、chitchat、web_research_write、direct_write 之一。"
                    "web_research_write 用于需要联网获取最新外部信息的请求（如天气、新闻、趋势、实时数据）。"
                    "direct_write 用于纯写作/生成类请求，不需要外部素材（如写感谢信、面试经验、润色改写）。"
                    "如果信息不足，请给出最可能的候选意图。",
                ),
                ("human", "示例：\n{few_shots}\n\n格式要求：\n{format_instructions}\n\n用户问题：{query}"),
            ]
        )
        chain = prompt | llm | parser
        try:
            result = await asyncio.wait_for(
                chain.ainvoke(
                    {
                        "few_shots": FEW_SHOTS,
                        "format_instructions": parser.get_format_instructions(),
                        "query": query,
                    }
                ),
                timeout=UTILITY_CLASSIFIER_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            result = IntentClassification(
                intent="chitchat",
                confidence=0.75,
                candidate_intents=["chitchat", "knowledge"],
                reason=f"意图分类超过 {UTILITY_CLASSIFIER_TIMEOUT_SECONDS:.1f}s，先按通用回答处理",
            )
    else:
        lowered = query.lower()
        date_result = _classify_local_datetime_query(query)
        if date_result is not None:
            result = date_result
        elif any(keyword in query for keyword in ["今天", "明天", "昨天", "最新", "最近", "2026", "趋势", "天气", "新闻", "查一下", "搜一下", "联网", "实时"]):
            result = IntentClassification(intent="web_research_write", confidence=0.8, candidate_intents=["web_research_write", "direct_write"], reason="命中了时效/联网类关键词")
        elif any(keyword in query for keyword in ["制度", "报销", "手册", "知识库", "规定"]) or "policy" in lowered:
            result = IntentClassification(intent="knowledge", confidence=0.82, candidate_intents=["knowledge", "travel"], reason="命中了制度类关键词")
        elif any(keyword in query for keyword in ["薪酬", "工资", "总包", "奖金"]):
            result = IntentClassification(intent="salary", confidence=0.9, candidate_intents=["salary", "personal"], reason="命中了薪酬类关键词")
        elif any(keyword in query for keyword in ["年假", "合同", "身份证", "手机号", "个人信息"]):
            result = IntentClassification(intent="personal", confidence=0.88, candidate_intents=["personal", "knowledge"], reason="命中了个人信息类关键词")
        elif any(keyword in query for keyword in ["机票", "酒店", "出差", "商旅", "预订"]):
            result = IntentClassification(intent="travel", confidence=0.91, candidate_intents=["travel", "knowledge"], reason="命中了出行类关键词")
        elif any(keyword in query for keyword in ["生成", "写", "撰写", "面试", "经验", "介绍", "总结", "润色", "改写"]):
            result = IntentClassification(intent="direct_write", confidence=0.75, candidate_intents=["direct_write", "web_research_write"], reason="命中了写作类关键词")
        else:
            result = IntentClassification(intent="chitchat", confidence=0.58, candidate_intents=["chitchat", "knowledge"], reason="未命中明确业务关键词")

    # 只有在"业务意图之间分不清"时才需要让用户澄清。
    # chitchat / direct_write / web_research_write 都是通用回答类，不需要高置信度。
    if (
        result.intent not in {"chitchat", "direct_write", "web_research_write"}
        and result.confidence < get_settings().intent_confidence_threshold
    ):
        result.intent = "clarify"
    return result
