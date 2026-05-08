"""结构化抽取链。"""

from __future__ import annotations

import re

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.core.llm import get_chat_model
from app.models.domain import PersonalQuery, TravelInfo
from app.services.travel_service import get_travel_service

# 城市名一般 2~3 个汉字（上海/深圳/北京/哈尔滨）。
# 之前用 {2,} 不限上限，会贪婪吞掉前面的 "下周二帮我预订上海" 这种。
# 这里用懒惰量词 {2,3}? 让两边都只取最近的城市名。
# 同时支持 "到/至/去/往/->/-" 这几种常见连接词。
CITY_PATTERN = re.compile(
    r"([\u4e00-\u9fff]{2,3}?)\s*(?:到|至|去|往|->|—|-)\s*([\u4e00-\u9fff]{2,3}?)(?=[，。,.!?\s的市省]|$)"
)
PASSENGER_PATTERN = re.compile(r"(\d+)\s*(?:位|个|人)")
TRAILING_NOISE = re.compile(r"[的市省]+$")


async def extract_travel_info(query: str) -> TravelInfo:
    """抽取商旅信息。"""
    parser = PydanticOutputParser(pydantic_object=TravelInfo)
    llm = get_chat_model(temperature=0, tags=["travel_extractor"])

    if llm is not None:
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是企业商旅助手，从用户的一句自然语言里抽取结构化出行信息。\n"
                    "硬性要求：\n"
                    "- from_city / to_city 只填**纯城市名**（如上海、深圳、哈尔滨），不要带任何修饰词、动词或时间。\n"
                    "- date 优先抽取「下周X」「明天」「YYYY-MM-DD」这种线索，找不到就填空字符串。\n"
                    "- passengers 是数字（默认 1）；cabin_class 只能填 '经济舱' / '商务舱' / '头等舱'。",
                ),
                (
                    "human",
                    "只输出符合 schema 的 JSON，不要任何解释。\n"
                    "{format_instructions}\n\n"
                    "用户输入：{query}",
                ),
            ]
        )
        chain = prompt | llm | parser
        try:
            result = await chain.ainvoke(
                {"query": query, "format_instructions": parser.get_format_instructions()}
            )
            return _sanitize_travel_info(result, query)
        except Exception:
            # LLM 抽取失败时降级到本地正则，保证主链路不挂。
            pass

    city_match = CITY_PATTERN.search(query)
    passenger_match = PASSENGER_PATTERN.search(query)
    from_city = TRAILING_NOISE.sub("", city_match.group(1)) if city_match else "上海"
    to_city = TRAILING_NOISE.sub("", city_match.group(2)) if city_match else "深圳"
    return TravelInfo(
        from_city=from_city or "上海",
        to_city=to_city or "深圳",
        date=get_travel_service().normalize_date_text(query),
        passengers=int(passenger_match.group(1)) if passenger_match else 1,
        cabin_class="商务舱" if "商务舱" in query else ("头等舱" if "头等舱" in query else "经济舱"),
    )


def _sanitize_travel_info(info: TravelInfo, query: str) -> TravelInfo:
    """LLM 偶尔会把动词、时间塞进城市字段，这里做最后一道清洗。"""
    from_city = TRAILING_NOISE.sub("", info.from_city.strip())
    to_city = TRAILING_NOISE.sub("", info.to_city.strip())
    # 城市名超过 4 个汉字基本是抽错了，回退到正则匹配。
    if len(from_city) > 4 or len(to_city) > 4 or not from_city or not to_city:
        city_match = CITY_PATTERN.search(query)
        if city_match:
            from_city = TRAILING_NOISE.sub("", city_match.group(1))
            to_city = TRAILING_NOISE.sub("", city_match.group(2))
    info.from_city = from_city or "上海"
    info.to_city = to_city or "深圳"
    return info


async def extract_personal_query(query: str) -> PersonalQuery:
    """抽取个人信息查询字段。"""
    parser = PydanticOutputParser(pydantic_object=PersonalQuery)
    llm = get_chat_model(temperature=0, tags=["personal_extractor"])

    if llm is not None:
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", "你负责从员工问题中提取目标用户和所需个人信息字段。"),
                ("human", "只输出 JSON。\n{format_instructions}\n\n用户问题：{query}"),
            ]
        )
        chain = prompt | llm | parser
        return await chain.ainvoke({"query": query, "format_instructions": parser.get_format_instructions()})

    requested_fields = []
    if "年假" in query:
        requested_fields.append("annual_leave")
    if "合同" in query:
        requested_fields.append("contract_end")
    if "部门" in query:
        requested_fields.append("department")
    if "手机号" in query or "电话" in query:
        requested_fields.append("phone")
    if "身份证" in query:
        requested_fields.append("id_card")
    return PersonalQuery(requested_fields=requested_fields or ["annual_leave", "contract_end"])
