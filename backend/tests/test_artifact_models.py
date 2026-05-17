"""共享 artifact 模型测试。"""

from __future__ import annotations

from app.models.artifacts import DateArtifact, DateArtifactData, WeatherArtifact, WeatherArtifactData


def test_artifact_models_round_trip() -> None:
    """天气卡片和日期卡片都应有稳定 kind 字段。"""
    weather = WeatherArtifact(
        data=WeatherArtifactData(
            city="深圳",
            relative_day_label="今天",
            forecast_date="2026-05-17",
            weekday_label="星期日",
            summary="多云",
            source_name="天气网",
        )
    )
    date = DateArtifact(
        data=DateArtifactData(
            title="今天",
            date_text="2026年05月17日",
            weekday_label="星期日",
            timezone="Asia/Shanghai",
        )
    )
    assert weather.kind == "weather_card"
    assert date.kind == "date_card"
