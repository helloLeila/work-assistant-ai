"""联网搜索节点。

这个节点干的事：当知识库搜不到答案时，去网上搜。
- 普通问题：百度/Google 搜一下，把结果拿回来给生成节点用
- 天气问题：会额外做 IP 定位、结构化抽取、生成天气卡片

上下游：
- 上游：grader_node 觉得知识库不够，路由到这里
- 下游：generate_node 用搜索结果生成最终回答
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import get_settings
from app.models.artifacts import ArtifactCompleteness, WeatherArtifact, WeatherArtifactData
from app.models.domain import WebSearchResult
from app.services.ip_location_service import contains_city_name, get_ip_location_service, is_weather_query
from app.services.weather_extractor import get_weather_extractor
from app.services.web_search_service import get_web_search_service


def _build_weather_clarify_message() -> str:
    """用户问天气但没说城市，也没法通过 IP 定位时，返回这句话引导用户补充城市。"""
    return "你想查哪个城市的天气？请直接告诉我具体城市，例如"深圳天气"。"


def _build_weather_unavailable_message(search_query: str) -> str:
    """天气查询失败时，告诉用户没查到。"""
    return f"我暂时没查到「{search_query}」的可信的最新天气数据。你可以稍后重试，或告诉我更具体的日期。"


def _get_local_today():
    """获取今天日期（按项目配置的时区，默认上海）。用来算"今天""明天"。"""
    settings = get_settings()
    timezone_name = settings.app_timezone.strip() or "Asia/Shanghai"
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return datetime.now().astimezone().date()
    return datetime.now(timezone).date()


def _format_weekday_label(value) -> str:
    """日期转中文星期，如"星期三"。"""
    weekday_labels = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")
    return weekday_labels[value.weekday()]


def _format_relative_weather_day(report) -> str:
    """把预报日期转成"今天""明天""后天"这种相对说法。

    跟今天比：差 0 天=今天，1 天=明天，2 天=后天，-1 天=昨天，
    再远就直接显示具体日期。
    """
    delta_days = (report.forecast_date - _get_local_today()).days
    if delta_days == 0:
        return "今天"
    if delta_days == 1:
        return "明天"
    if delta_days == 2:
        return "后天"
    if delta_days == -1:
        return "昨天"
    return report.forecast_date.strftime("%Y年%m月%d日")


def _build_weather_message(report) -> str:
    """把天气数据拼接成人话。

    输入：结构化天气数据（城市、日期、气温、天气状况等）
    输出："北京今天（2026年05月21日，星期三）天气：晴，最低气温 15°C..."
    """
    details: list[str] = []
    if report.condition:
        details.append(report.condition)
    if report.temp_low_c is not None and report.temp_high_c is not None:
        if report.temp_low_c == report.temp_high_c:
            details.append(f"气温 {report.temp_high_c}°C")
        else:
            details.append(f"最低气温 {report.temp_low_c}°C")
            details.append(f"最高气温 {report.temp_high_c}°C")
    elif report.current_temp_c is not None:
        details.append(f"当前气温 {report.current_temp_c}°C")
    if report.feels_like_c is not None:
        details.append(f"体感 {report.feels_like_c}°C")
    if report.wind_text:
        details.append(report.wind_text)
    if report.air_quality:
        details.append(f"空气质量{report.air_quality}")

    body = "，".join(details) if details else "天气信息待确认"
    relative_day = _format_relative_weather_day(report)
    date_text = report.forecast_date.strftime("%Y年%m月%d日")
    weekday_text = _format_weekday_label(report.forecast_date)
    return f"{report.city}{relative_day}（{date_text}，{weekday_text}）天气：{body}。来源：{report.source_name}。"


def _build_weather_artifact(report) -> dict[str, object]:
    """把天气数据打包成前端天气卡片需要的格式。

    前端拿到这个数据，就能渲染出一个漂亮的天气卡片，
    显示城市、日期、气温、天气状况、空气质量等。
    """
    temp_low_c = report.temp_low_c
    temp_high_c = report.temp_high_c
    if temp_low_c is None and temp_high_c is None and report.current_temp_c is not None:
        temp_low_c = report.current_temp_c
        temp_high_c = report.current_temp_c

    completeness = ArtifactCompleteness(
        has_current=report.current_temp_c is not None,
        has_forecast=True,
        missing_fields=[
            field
            for field, value in (
                ("current_temp_c", report.current_temp_c),
                ("temp_low_c", temp_low_c),
                ("temp_high_c", temp_high_c),
                ("feels_like_c", report.feels_like_c),
                ("wind_text", report.wind_text),
                ("air_quality", report.air_quality),
            )
            if value in (None, "")
        ],
    )
    artifact = WeatherArtifact(
        data=WeatherArtifactData(
            city=report.city,
            relative_day_label=_format_relative_weather_day(report),
            forecast_date=report.forecast_date.isoformat(),
            weekday_label=_format_weekday_label(report.forecast_date),
            summary=report.condition,
            current_temp_c=report.current_temp_c,
            temp_low_c=temp_low_c,
            temp_high_c=temp_high_c,
            feels_like_c=report.feels_like_c,
            wind_text=report.wind_text,
            air_quality=report.air_quality,
            source_name=report.source_name,
            source_url=report.source_url,
            completeness=completeness,
        )
    )
    return artifact.model_dump()


def _build_web_sources(result: WebSearchResult) -> list[dict[str, object]]:
    """把网页搜索结果转成和知识库 sources 一样的格式。

    这样下游节点（generate_node）不用区分是网页搜的还是知识库搜的，
    统一处理就行。
    """
    sources: list[dict[str, object]] = []
    for index, item in enumerate(result.results[:5], start=1):
        sources.append(
            {
                "doc_id": item.url or f"web-{index}",
                "source_file": item.site_name or item.title or f"网页结果 {index}",
                "page_num": index,
                "department": "web",
                "score": 1.0,
                "snippet": item.snippet or item.title,
            }
        )
    return sources


def _format_search_context(result: WebSearchResult) -> str:
    """把网页搜索结果整理成一段话，给 LLM 当参考资料用。

    格式：先写搜索主题，然后逐条列出标题、来源、摘要。
    """
    lines = [f"联网搜索主题：{result.query}"]
    for index, item in enumerate(result.results[:5], start=1):
        source = item.site_name or item.title or "网页来源"
        snippet = item.snippet.strip() or item.title
        lines.append(f"{index}. 标题：{item.title}；来源：{source}；摘要：{snippet}")
    return "\n".join(lines)


async def _augment_weather_query(query: str, client_ip: str | None) -> str | None:
    """天气查询补城市。

    用户说"今天天气怎么样"但没提城市，这个函数会根据 IP 推断城市，
    变成"北京 今天天气怎么样"再拿去搜，不然搜不到。

    处理逻辑：
    1. 不是天气问题？直接返回原话，不用补
    2. 已经说了城市？直接返回原话，不用补
    3. 没 IP 地址？返回 None，让外面提示用户说城市
    4. 有 IP 但定位失败？返回 None，同样提示用户
    5. 定位成功？返回"城市名 + 原话"

    参数：
    - query: 用户原话
    - client_ip: 用户 IP，用来定位城市

    返回值：
    - str: 补了城市的话，或者不用补的原话
    - None: 需要补但补不了，外面要提示用户
    """
    if not is_weather_query(query):
        return query
    if contains_city_name(query):
        return query
    if not client_ip:
        return None
    city = await get_ip_location_service().lookup(client_ip)
    if not city:
        return None
    return f"{city} {query}"


async def web_search_node(state: dict) -> dict:
    """联网搜索节点。

    什么时候进来：grader_node 觉得知识库搜出来的东西不够回答用户问题时，
    就会路由到这里，去网上搜一圈补充一下。

    两条路径：
    1. 天气问题：先补城市名（用 IP 定位），然后搜天气，
       抽结构化数据，生成天气消息 + 天气卡片
    2. 普通问题：直接搜网页，把结果整理成文本给 LLM 用

    各种异常情况的处理：
    - Bocha API 关了 → 返回"搜索暂时不可用"
    - 搜了但结果为空 → 返回"没查到结果"
    - 天气搜了但抽不出数据 → 返回"没查到可信天气数据"

    参数：
    - state: 工作流状态，必须有 "query"（用户问题），
      可选有 "client_ip"（用户 IP，天气定位用）

    返回值：
    - structured_data: 搜索回来的内容（天气消息/网页摘要/错误提示）
    - sources: 网页来源列表（普通搜索时）
    - artifacts: 天气卡片数据（天气搜索时）
    """
    query = str(state["query"]).strip()
    weather_query = is_weather_query(query)
    search_query = await _augment_weather_query(query, state.get("client_ip"))

    if weather_query and search_query is None:
        return {"structured_data": {"message": _build_weather_clarify_message()}}

    effective_query = search_query or query
    if not get_settings().bocha_enabled:
        if weather_query:
            return {"structured_data": {"message": _build_weather_unavailable_message(effective_query)}}
        return {
            "structured_data": {
                "web_search_failed": True,
                "message": "联网搜索暂时不可用，请稍后重试。",
            }
        }

    try:
        result = await get_web_search_service().search(
            effective_query,
            freshness="oneDay" if weather_query else None,
        )
    except Exception:
        if weather_query:
            return {"structured_data": {"message": _build_weather_unavailable_message(effective_query)}}
        return {
            "structured_data": {
                "web_search_failed": True,
                "message": "联网搜索暂时不可用，请稍后重试。",
            }
        }

    if not result.results:
        if weather_query:
            return {"structured_data": {"message": _build_weather_unavailable_message(effective_query)}}
        return {
            "structured_data": {
                "web_search_failed": True,
                "message": f"暂时没有查到「{effective_query}」的联网结果。",
            }
        }

    sources = _build_web_sources(result)
    if weather_query:
        report = get_weather_extractor().extract(
            query=query,
            search_query=effective_query,
            results=result.results,
        )
        if report is None:
            return {"structured_data": {"message": _build_weather_unavailable_message(effective_query)}}
        return {
            "structured_data": {
                "message": _build_weather_message(report),
                "weather_report": report.to_dict(),
            },
            "artifacts": [_build_weather_artifact(report)],
            "sources": sources,
        }

    return {
        "structured_data": {"web_search_result": _format_search_context(result)},
        "sources": sources,
    }
