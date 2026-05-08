"""意图分类链。"""

from __future__ import annotations

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.core.config import get_settings
from app.core.llm import get_chat_model
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
""".strip()


async def classify_intent(query: str) -> IntentClassification:
    """执行意图分类。"""
    parser = PydanticOutputParser(pydantic_object=IntentClassification)
    llm = get_chat_model(temperature=0, tags=["intent_router"])

    if llm is not None:
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是企业智能办公助手的意图分类器。请根据用户问题返回 JSON。"
                    "意图只能是 knowledge、salary、personal、travel、chitchat 之一。"
                    "如果信息不足，请给出最可能的候选意图。",
                ),
                ("human", "示例：\n{few_shots}\n\n格式要求：\n{format_instructions}\n\n用户问题：{query}"),
            ]
        )
        chain = prompt | llm | parser
        result = await chain.ainvoke(
            {
                "few_shots": FEW_SHOTS,
                "format_instructions": parser.get_format_instructions(),
                "query": query,
            }
        )
    else:
        lowered = query.lower()
        if any(keyword in query for keyword in ["制度", "报销", "手册", "知识库", "规定"]) or "policy" in lowered:
            result = IntentClassification(intent="knowledge", confidence=0.82, candidate_intents=["knowledge", "travel"], reason="命中了制度类关键词")
        elif any(keyword in query for keyword in ["薪酬", "工资", "总包", "奖金"]):
            result = IntentClassification(intent="salary", confidence=0.9, candidate_intents=["salary", "personal"], reason="命中了薪酬类关键词")
        elif any(keyword in query for keyword in ["年假", "合同", "身份证", "手机号", "个人信息"]):
            result = IntentClassification(intent="personal", confidence=0.88, candidate_intents=["personal", "knowledge"], reason="命中了个人信息类关键词")
        elif any(keyword in query for keyword in ["机票", "酒店", "出差", "商旅", "预订"]):
            result = IntentClassification(intent="travel", confidence=0.91, candidate_intents=["travel", "knowledge"], reason="命中了出行类关键词")
        else:
            result = IntentClassification(intent="chitchat", confidence=0.58, candidate_intents=["chitchat", "knowledge"], reason="未命中明确业务关键词")

    # 只有在“业务意图之间分不清”时才需要让用户澄清。
    # chitchat 本身就不需要高置信度，直接放过去由 generate_node 用模型回答。
    if (
        result.intent != "chitchat"
        and result.confidence < get_settings().intent_confidence_threshold
    ):
        result.intent = "clarify"
    return result
