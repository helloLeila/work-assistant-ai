"""商旅服务。"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from functools import lru_cache
from uuid import uuid4

import httpx

from app.core.config import get_settings
from app.models.domain import TravelInfo, TravelOrder

EXACT_DATE_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2})")
WEEKDAY_MAP = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}


class TravelService:
    """处理商旅申请。"""

    def normalize_date_text(self, text: str) -> str:
        """把相对日期转换成日期文本。"""
        exact_date_match = EXACT_DATE_PATTERN.search(text)
        if exact_date_match:
            return exact_date_match.group(1)

        next_week_match = re.search(r"下周([一二三四五六日天])", text)
        if next_week_match:
            return self._resolve_weekday_date(WEEKDAY_MAP[next_week_match.group(1)], include_next_week=True)

        current_week_match = re.search(r"周([一二三四五六日天])", text)
        if current_week_match:
            return self._resolve_weekday_date(WEEKDAY_MAP[current_week_match.group(1)], include_next_week=False)

        if "明天" in text:
            return (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        if "后天" in text:
            return (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
        return text

    def create_order(self, travel_info: TravelInfo) -> TravelOrder:
        """创建商旅订单，优先转发到外部系统。"""
        settings = get_settings()

        if settings.travel_api_base_url:
            try:
                # 一旦配置了第三方地址，优先按正式集成方式调用外部接口。
                return self._forward_order(travel_info)
            except Exception:
                # 是否允许回退由配置决定。
                # 面试展示、离线开发或第三方接口暂未就绪时，通常保持 true。
                if not settings.travel_api_fallback_enabled:
                    raise

        return self._create_local_order(travel_info)

    def _create_local_order(self, travel_info: TravelInfo) -> TravelOrder:
        """返回本地订单结果，用于开发环境回退。"""
        order_id = f"TRV-{uuid4().hex[:8].upper()}"
        return TravelOrder(
            order_id=order_id,
            status="confirmed",
            itinerary_summary=self._build_summary(travel_info),
            provider="local",
        )

    def _forward_order(self, travel_info: TravelInfo) -> TravelOrder:
        """调用外部商旅接口。"""
        settings = get_settings()
        api_url = f"{settings.travel_api_base_url.rstrip('/')}/{settings.travel_api_path.lstrip('/')}"
        headers = {"Content-Type": "application/json"}
        if settings.travel_api_auth_token:
            headers["Authorization"] = f"Bearer {settings.travel_api_auth_token}"

        response = httpx.post(
            api_url,
            json=travel_info.model_dump(),
            headers=headers,
            timeout=settings.travel_api_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()

        # 这里兼容不同商旅供应商的字段命名差异，
        # 避免因为返回字段不完全一致而直接让主链路失败。
        return TravelOrder(
            order_id=str(payload.get("order_id") or payload.get("id") or f"EXT-{uuid4().hex[:8].upper()}"),
            status=str(payload.get("status") or "submitted"),
            itinerary_summary=str(payload.get("itinerary_summary") or payload.get("summary") or self._build_summary(travel_info)),
            provider=str(payload.get("provider") or self._extract_provider_name(settings.travel_api_base_url)),
            booking_reference=self._string_or_none(payload.get("booking_reference") or payload.get("reference")),
        )

    def _resolve_weekday_date(self, weekday: int, *, include_next_week: bool) -> str:
        """把周几表达转成具体日期。"""
        today = datetime.now()
        days_ahead = (weekday - today.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        if include_next_week:
            days_ahead += 7
        return (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    @staticmethod
    def _build_summary(travel_info: TravelInfo) -> str:
        """生成统一的行程摘要。"""
        return (
            f"{travel_info.date} {travel_info.from_city} -> {travel_info.to_city}，"
            f"{travel_info.passengers}位乘客，{travel_info.cabin_class}"
        )

    @staticmethod
    def _extract_provider_name(base_url: str) -> str:
        """从外部接口地址推断供应商名称。"""
        return base_url.replace("https://", "").replace("http://", "").strip("/") or "external"

    @staticmethod
    def _string_or_none(value: object) -> str | None:
        """把可选字段转成字符串。"""
        if value in {None, ""}:
            return None
        return str(value)


@lru_cache
def get_travel_service() -> TravelService:
    return TravelService()


def get_travel_module_snapshot() -> dict[str, str]:
    return {
        "name": "商旅代办",
        "status": "已启用",
        "highlight": "支持结构化抽取、外部接口转发与本地下单回退",
        "capability": "支持出发地、目的地、日期、人数和舱位解析",
    }
