"""Bocha Web Search 服务封装。"""

from __future__ import annotations

from functools import lru_cache

import httpx

from app.core.config import get_settings
from app.models.domain import WebSearchHit, WebSearchResult


class WebSearchService:
    """联网搜索服务。超时/失败即抛异常，由调用方降级。"""

    async def search(
        self,
        query: str,
        *,
        max_results: int | None = None,
        freshness: str | None = None,
    ) -> WebSearchResult:
        settings = get_settings()
        limit = max_results if max_results is not None else settings.bocha_max_results
        url = f"{settings.bocha_base_url.rstrip('/')}/web-search"

        payload = {
            "query": query,
            "count": limit,
            "freshness": freshness or settings.bocha_freshness,
            "summary": True,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {settings.bocha_api_key}",
                    "Content-Type": "application/json",
                },
                timeout=settings.bocha_timeout_seconds,
            )
            response.raise_for_status()
            data = response.json().get("data", {})

        return self._parse_response(data, query)

    def _parse_response(self, data: dict, query: str) -> WebSearchResult:
        """把 Bocha 返回解析为统一结构。schema 变化时只改这里。"""
        hits: list[WebSearchHit] = []
        raw_results = data.get("webPages", {}).get("value", [])
        for item in raw_results:
            hits.append(
                WebSearchHit(
                    title=str(item.get("name") or ""),
                    url=str(item.get("url") or ""),
                    snippet=str(item.get("summary") or item.get("snippet") or ""),
                    site_name=str(item.get("siteName") or ""),
                    published_at=str(item.get("datePublished") or ""),
                )
            )

        return WebSearchResult(
            query=query,
            results=hits,
            elapsed_ms=data.get("elapsed_ms", 0),
        )


@lru_cache
def get_web_search_service() -> WebSearchService:
    return WebSearchService()


def get_web_search_module_snapshot() -> dict[str, str]:
    return {
        "name": "Bocha 联网搜索",
        "status": "已启用" if get_settings().bocha_enabled else "未配置",
        "highlight": "国内直连，超时自动降级",
        "capability": "支持时效过滤、摘要提取、来源溯源",
    }
