"""外部补充检索节点。"""

from __future__ import annotations

from app.core.config import get_settings
from app.models.domain import WebSearchResult
from app.services.ip_location_service import contains_city_name, get_ip_location_service, is_weather_query
from app.services.weather_extractor import get_weather_extractor
from app.services.web_search_service import get_web_search_service


def _build_weather_clarify_message() -> str:
    return "你想查哪个城市的天气？请直接告诉我具体城市，例如“深圳天气”。"


def _build_weather_unavailable_message(search_query: str) -> str:
    return f"我暂时没查到「{search_query}」的可信的最新天气数据。你可以稍后重试，或告诉我更具体的日期。"


def _build_weather_message(report) -> str:
    temp_part = ""
    if report.temp_low_c is not None and report.temp_high_c is not None:
        if report.temp_low_c == report.temp_high_c:
            temp_part = f"{report.temp_high_c}°C"
        else:
            temp_part = f"{report.temp_low_c}~{report.temp_high_c}°C"

    body = report.condition
    if temp_part:
        body = f"{body}，{temp_part}"
    return (
        f"{report.city} {report.forecast_date.isoformat()} 天气：{body}。"
        f"来源：{report.source_name}。"
    )


def _build_web_sources(result: WebSearchResult) -> list[dict[str, object]]:
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
    lines = [f"联网搜索主题：{result.query}"]
    for index, item in enumerate(result.results[:5], start=1):
        source = item.site_name or item.title or "网页来源"
        snippet = item.snippet.strip() or item.title
        lines.append(f"{index}. 标题：{item.title}；来源：{source}；摘要：{snippet}")
    return "\n".join(lines)


async def _augment_weather_query(query: str, client_ip: str | None) -> str | None:
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
    """联网搜索节点；天气查询会单独做 freshness/抽取/日期校验。"""
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
            "sources": sources,
        }

    return {
        "structured_data": {"web_search_result": _format_search_context(result)},
        "sources": sources,
    }
