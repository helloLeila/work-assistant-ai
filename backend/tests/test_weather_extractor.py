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


def test_extract_previous_day_weather_for_today_query_returns_none() -> None:
    extractor = WeatherExtractor()
    hit = WebSearchHit(
        title="天津天气预报",
        url="https://weather.example.com/tianjin",
        snippet="2026年05月16日天津天气预报：多云，温度:25/4°C，西南风3级。",
        site_name="互联百科",
    )

    report = extractor.extract(
        query="天津天气",
        search_query="天津 天气",
        results=[hit],
        today=date(2026, 5, 17),
    )

    assert report is None


def test_extract_weather_with_high_low_celsius_symbol() -> None:
    extractor = WeatherExtractor()
    hit = WebSearchHit(
        title="天津天气预报",
        url="https://weather.example.com/tianjin",
        snippet="天津今日天气：晴，最高温31℃，最低温18℃，西南风3级。",
        site_name="天气网",
    )

    report = extractor.extract(
        query="天津天气",
        search_query="天津 天气",
        results=[hit],
        today=date(2026, 5, 17),
    )

    assert report is not None
    assert report.temp_high_c == 31
    assert report.temp_low_c == 18
    assert report.wind_text == "西南风3级"


def test_extract_weather_with_range_and_air_quality() -> None:
    extractor = WeatherExtractor()
    hit = WebSearchHit(
        title="天津天气预报",
        url="https://weather.example.com/tianjin",
        snippet="5月17日 小雨气温18~24℃，东风转东北风1-3级。空气质量为优。",
        site_name="中国天气网",
    )

    report = extractor.extract(
        query="天津天气",
        search_query="天津 天气",
        results=[hit],
        today=date(2026, 5, 17),
    )

    assert report is not None
    assert report.temp_high_c == 24
    assert report.temp_low_c == 18
    assert report.wind_text == "东风转东北风1-3级"
    assert report.air_quality == "优"


def test_extract_weather_without_explicit_date_falls_back_to_target_date() -> None:
    extractor = WeatherExtractor()
    hit = WebSearchHit(
        title="天津天气预报",
        url="https://weather.example.com/tianjin",
        snippet="天津天气：晴，31°C/18°C。",
        site_name="天气网",
    )

    report = extractor.extract(
        query="天津天气",
        search_query="天津 天气",
        results=[hit],
        today=date(2026, 5, 17),
    )

    assert report is not None
    assert report.forecast_date == date(2026, 5, 17)
    assert report.temp_high_c == 31
    assert report.temp_low_c == 18


def test_extract_prefers_richer_trusted_weather_source() -> None:
    extractor = WeatherExtractor()
    low_quality_hit = WebSearchHit(
        title="天津天气 - 互联百科",
        url="https://example.com/tianjin-weather",
        snippet="2026年05月17日天津天气：多云，温度:25/4°C，风。",
        site_name="互联百科",
    )
    trusted_hit = WebSearchHit(
        title="天津天气预报",
        url="https://www.weather.com.cn/weather/101030100.shtml",
        snippet="2026年05月17日天津天气预报：多云，温度:25/4°C，西南风3级，空气质量为良。",
        site_name="中国天气网",
    )

    report = extractor.extract(
        query="天津天气",
        search_query="天津 天气",
        results=[low_quality_hit, trusted_hit],
        today=date(2026, 5, 17),
    )

    assert report is not None
    assert report.source_name == "中国天气网"
    assert report.wind_text == "西南风3级"
    assert report.air_quality == "良"


def test_extract_does_not_parse_wind_level_as_temperature_range() -> None:
    extractor = WeatherExtractor()
    hit = WebSearchHit(
        title="上海天气预报",
        url="https://example.com/shanghai-weather",
        snippet="2026年05月18日上海天气：多云，东北风3-4级，空气质量良。",
        site_name="今日头条",
    )

    report = extractor.extract(
        query="上海天气",
        search_query="上海 天气",
        results=[hit],
        today=date(2026, 5, 18),
    )

    assert report is not None
    assert report.temp_low_c is None
    assert report.temp_high_c is None
    assert report.wind_text == "东北风3-4级"
