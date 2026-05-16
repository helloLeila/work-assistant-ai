"""天气摘要归一化抽取测试。"""

from __future__ import annotations

from datetime import date

from app.models.domain import WebSearchHit
from app.services.weather_extractor import WeatherExtractor


def test_extract_recent_weather_hit_returns_normalized_report() -> None:
    extractor = WeatherExtractor()
    hit = WebSearchHit(
        title="深圳天气预报",
        url="https://weather.example.com/shenzhen",
        snippet="2026年05月16日深圳天气预报：多云，温度:26/20°C，南风3级。",
        site_name="天气网",
    )

    report = extractor.extract(
        query="深圳天气",
        search_query="深圳 天气",
        results=[hit],
        today=date(2026, 5, 16),
    )

    assert report is not None
    assert report.city == "深圳"
    assert report.forecast_date == date(2026, 5, 16)
    assert report.condition == "多云"
    assert report.temp_high_c == 26
    assert report.temp_low_c == 20
    assert report.source_name == "天气网"


def test_extract_stale_weather_hit_returns_none() -> None:
    extractor = WeatherExtractor()
    hit = WebSearchHit(
        title="深圳天气预报",
        url="https://weather.example.com/shenzhen",
        snippet=(
            "2026年04月25日深圳天气预报: 04/25 (周六): 天气:多云转晴,"
            "温度:26/20°C,风向风力:无持续风向<3级"
        ),
        site_name="天气网",
    )

    report = extractor.extract(
        query="深圳天气",
        search_query="深圳 天气",
        results=[hit],
        today=date(2026, 5, 16),
    )

    assert report is None
