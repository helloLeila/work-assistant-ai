"""IP 到城市的定位服务。"""

from __future__ import annotations

import ipaddress
import time
from collections import deque
from functools import lru_cache

import httpx

_KNOWN_CITIES = {
    "北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "西安", "南京",
    "重庆", "天津", "苏州", "长沙", "郑州", "青岛", "大连", "厦门", "昆明",
    "哈尔滨", "沈阳", "济南", "无锡", "宁波", "佛山", "东莞", "石家庄",
    "太原", "合肥", "南昌", "福州", "南宁", "贵阳", "兰州", "海口",
    "乌鲁木齐", "拉萨", "银川", "西宁", "呼和浩特", "长春",
}

_WEATHER_KEYWORDS = {
    "天气", "气温", "温度", "forecast",
    "冷不冷", "热不热", "下雨", "下雪", "刮风", "台风", "雾霾",
    "空气质量", "穿衣指数", "紫外线",
}

_TIME_MODIFIERS = {"今天", "明天", "后天", "下周", "最近"}


class IPLocationService:
    """IP 到城市的定位服务。"""

    def __init__(self) -> None:
        self._cache: dict[str, tuple[str, float]] = {}
        self._ttl_seconds = 300
        self._rate_limit = 150
        self._window_seconds = 60
        self._call_times: deque[float] = deque()

    def _is_private_ip(self, ip: str) -> bool:
        try:
            addr = ipaddress.ip_address(ip)
            return addr.is_private or addr.is_loopback or addr.is_link_local
        except ValueError:
            return True

    def _mask_ip(self, ip: str) -> str:
        parts = ip.split(".")
        if len(parts) == 4:
            parts[3] = "0"
            return ".".join(parts)
        return ip

    def _is_rate_limited(self) -> bool:
        now = time.time()
        while self._call_times and self._call_times[0] < now - self._window_seconds:
            self._call_times.popleft()
        return len(self._call_times) >= self._rate_limit

    def _get_cached(self, masked_ip: str) -> str | None:
        if masked_ip in self._cache:
            city, ts = self._cache[masked_ip]
            if time.time() - ts < self._ttl_seconds:
                return city
            del self._cache[masked_ip]
        return None

    async def lookup(self, ip: str) -> str | None:
        if self._is_private_ip(ip):
            return None

        masked = self._mask_ip(ip)
        cached = self._get_cached(masked)
        if cached is not None:
            return cached

        if self._is_rate_limited():
            return None

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"http://ip-api.com/json/{masked}?lang=zh-CN",
                    timeout=2.0,
                )
                self._call_times.append(time.time())
                resp.raise_for_status()
                data = resp.json()
                if data.get("status") == "success":
                    city = data.get("city")
                    if city:
                        self._cache[masked] = (city, time.time())
                        return city
        except (httpx.HTTPError, TimeoutError):
            pass
        return None


@lru_cache
def get_ip_location_service() -> IPLocationService:
    return IPLocationService()


def is_weather_query(query: str) -> bool:
    query = query.strip()
    if any(keyword in query for keyword in _WEATHER_KEYWORDS):
        return True
    if any(modifier in query for modifier in _TIME_MODIFIERS):
        return any(keyword in query for keyword in {"天气", "气温", "温度", "下雨", "下雪", "刮风", "台风", "雾霾"})
    return False


def contains_city_name(query: str) -> bool:
    return any(city in query for city in _KNOWN_CITIES)
