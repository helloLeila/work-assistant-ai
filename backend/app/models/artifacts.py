"""聊天 artifact 共享模型。

这些结构会同时被后端 SSE、历史记录和前端 Vue props 使用，所以字段名和类型必须稳定。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class WeatherForecastItem(BaseModel):
    """天气预报列表中的单个未来日期项。"""

    date: str
    weekday_label: str
    relative_day_label: str
    condition: str
    temp_low_c: int | None = None
    temp_high_c: int | None = None


class ArtifactCompleteness(BaseModel):
    """天气卡片信息完整度，用来让前端决定是否显示扩展字段。"""

    has_current: bool = False
    has_forecast: bool = False
    missing_fields: list[str] = Field(default_factory=list)


class WeatherArtifactData(BaseModel):
    """天气卡片的结构化载荷。"""

    city: str
    relative_day_label: str
    forecast_date: str
    weekday_label: str
    summary: str
    current_temp_c: int | None = None
    temp_low_c: int | None = None
    temp_high_c: int | None = None
    feels_like_c: int | None = None
    wind_text: str = ""
    air_quality: str = ""
    humidity: str = ""
    precipitation: str = ""
    uv_index: str = ""
    source_name: str
    source_url: str = ""
    forecast_items: list[WeatherForecastItem] = Field(default_factory=list)
    completeness: ArtifactCompleteness = Field(default_factory=ArtifactCompleteness)


class DateArtifactData(BaseModel):
    """日期卡片的结构化载荷。"""

    title: str
    date_text: str
    weekday_label: str
    timezone: str


class WeatherArtifact(BaseModel):
    """天气卡片 artifact，kind 作为前后端分发的稳定路由键。"""

    kind: Literal["weather_card"] = "weather_card"
    version: int = 1
    data: WeatherArtifactData


class DateArtifact(BaseModel):
    """日期卡片 artifact，kind 作为前后端分发的稳定路由键。"""

    kind: Literal["date_card"] = "date_card"
    version: int = 1
    data: DateArtifactData
