"""天气搜索结果归一化抽取。"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from functools import lru_cache

from app.models.domain import WebSearchHit

_YEAR_DATE_PATTERN = re.compile(r"(20\d{2})[年\-/\.](\d{1,2})[月\-/\.](\d{1,2})日?")
_MONTH_DAY_SLASH_PATTERN = re.compile(r"(?<!\d)(\d{1,2})[/-](\d{1,2})(?!\d)")
_MONTH_DAY_CN_PATTERN = re.compile(r"(?<!\d)(\d{1,2})月(\d{1,2})日")
_QUERY_EXPLICIT_DATE_PATTERN = re.compile(r"(20\d{2})?[年\-/\.]?\s*(\d{1,2})月?\s*(\d{1,2})日?")
_TEMP_RANGE_PATTERN = re.compile(r"(?:温度|气温)?[:：]?\s*(-?\d{1,2})\s*[/~-]\s*(-?\d{1,2})\s*°?\s*C", re.IGNORECASE)
_TEMP_SINGLE_PATTERN = re.compile(r"(?:温度|气温|体感)[:：]?\s*(-?\d{1,2})\s*°?\s*C", re.IGNORECASE)

_WEATHER_LABELS = (
    "雷阵雨转多云",
    "多云转雷阵雨",
    "雷阵雨转大雨",
    "大雨转雷阵雨",
    "多云转晴",
    "晴转多云",
    "多云转雨",
    "雨转多云",
    "多云转阴",
    "阴转多云",
    "暴雨",
    "大雨",
    "中雨",
    "小雨",
    "雷阵雨",
    "阵雨",
    "多云",
    "晴",
    "阴",
    "雾",
    "霾",
    "雪",
)


@dataclass(frozen=True)
class WeatherReport:
    city: str
    target_date: date
    forecast_date: date
    condition: str
    temp_low_c: int | None
    temp_high_c: int | None
    source_name: str
    source_url: str

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["target_date"] = self.target_date.isoformat()
        payload["forecast_date"] = self.forecast_date.isoformat()
        return payload


class WeatherExtractor:
    """从通用搜索摘要中抽取有限的天气结构。"""

    def extract(
        self,
        *,
        query: str,
        search_query: str,
        results: list[WebSearchHit],
        today: date | None = None,
    ) -> WeatherReport | None:
        current_day = today or date.today()
        target_date = self._infer_target_date(query, current_day)
        city = self._infer_city(query, search_query)

        for hit in results:
            report = self._normalize_hit(
                hit=hit,
                city=city,
                target_date=target_date,
                today=current_day,
            )
            if report is not None:
                return report
        return None

    def _normalize_hit(
        self,
        *,
        hit: WebSearchHit,
        city: str,
        target_date: date,
        today: date,
    ) -> WeatherReport | None:
        text = " ".join(part for part in (hit.title, hit.snippet, hit.published_at) if part)
        dates = self._extract_dates(text, today)
        if not dates:
            return None

        forecast_date = self._pick_matching_date(dates, target_date)
        if forecast_date is None:
            return None

        condition = self._extract_condition(text)
        temp_low_c, temp_high_c = self._extract_temperatures(text)
        if not condition and temp_low_c is None and temp_high_c is None:
            return None

        return WeatherReport(
            city=city,
            target_date=target_date,
            forecast_date=forecast_date,
            condition=condition or "天气信息待确认",
            temp_low_c=temp_low_c,
            temp_high_c=temp_high_c,
            source_name=hit.site_name or hit.title or "网页来源",
            source_url=hit.url,
        )

    def _infer_city(self, query: str, search_query: str) -> str:
        for candidate in (search_query, query):
            cleaned = candidate.replace("天气", " ").replace("气温", " ").replace("温度", " ")
            parts = [part.strip() for part in cleaned.split() if part.strip()]
            if parts:
                return parts[0]
        return "当地"

    def _infer_target_date(self, query: str, today: date) -> date:
        if "后天" in query:
            return today + timedelta(days=2)
        if "明天" in query:
            return today + timedelta(days=1)
        if "昨天" in query:
            return today - timedelta(days=1)

        explicit = self._extract_query_explicit_date(query, today)
        if explicit is not None:
            return explicit
        return today

    def _extract_query_explicit_date(self, query: str, today: date) -> date | None:
        match = _QUERY_EXPLICIT_DATE_PATTERN.search(query)
        if not match:
            return None
        year_text, month_text, day_text = match.groups()
        month = int(month_text)
        day = int(day_text)
        year = int(year_text) if year_text else today.year
        try:
            return date(year, month, day)
        except ValueError:
            return None

    def _extract_dates(self, text: str, today: date) -> list[date]:
        seen: set[date] = set()
        dates: list[date] = []

        for year_text, month_text, day_text in _YEAR_DATE_PATTERN.findall(text):
            try:
                candidate = date(int(year_text), int(month_text), int(day_text))
            except ValueError:
                continue
            if candidate not in seen:
                seen.add(candidate)
                dates.append(candidate)

        for month_text, day_text in _MONTH_DAY_CN_PATTERN.findall(text):
            candidate = self._coerce_month_day(today.year, month_text, day_text)
            if candidate is not None and candidate not in seen:
                seen.add(candidate)
                dates.append(candidate)

        for month_text, day_text in _MONTH_DAY_SLASH_PATTERN.findall(text):
            candidate = self._coerce_month_day(today.year, month_text, day_text)
            if candidate is not None and candidate not in seen:
                seen.add(candidate)
                dates.append(candidate)

        return dates

    def _coerce_month_day(self, year: int, month_text: str, day_text: str) -> date | None:
        month = int(month_text)
        day = int(day_text)
        if not 1 <= month <= 12:
            return None
        try:
            return date(year, month, day)
        except ValueError:
            return None

    def _pick_matching_date(self, dates: list[date], target_date: date) -> date | None:
        window_start = target_date - timedelta(days=1)
        window_end = target_date + timedelta(days=1)
        candidates = [candidate for candidate in dates if window_start <= candidate <= window_end]
        if not candidates:
            return None
        return min(candidates, key=lambda candidate: abs((candidate - target_date).days))

    def _extract_condition(self, text: str) -> str:
        best_label = ""
        best_index: int | None = None
        for label in _WEATHER_LABELS:
            index = text.find(label)
            if index == -1:
                continue
            if best_index is None or index < best_index or (index == best_index and len(label) > len(best_label)):
                best_label = label
                best_index = index
        return best_label

    def _extract_temperatures(self, text: str) -> tuple[int | None, int | None]:
        match = _TEMP_RANGE_PATTERN.search(text)
        if match:
            first = int(match.group(1))
            second = int(match.group(2))
            return min(first, second), max(first, second)

        match = _TEMP_SINGLE_PATTERN.search(text)
        if match:
            value = int(match.group(1))
            return value, value

        return None, None


@lru_cache
def get_weather_extractor() -> WeatherExtractor:
    return WeatherExtractor()
