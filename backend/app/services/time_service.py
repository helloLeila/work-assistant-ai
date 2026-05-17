"""本地时间与日期卡片辅助。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import get_settings
from app.models.artifacts import DateArtifact, DateArtifactData

WEEKDAY_LABELS = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")


@dataclass(frozen=True)
class LocalTimeContext:
    """本地时区下的日期快照。"""

    now: datetime
    timezone_name: str
    date_text: str
    weekday_label: str


def get_local_time_context() -> LocalTimeContext:
    """读取配置里的本地时区，并格式化成日期/星期文本。"""
    settings = get_settings()
    timezone_name = settings.app_timezone.strip() or "Asia/Shanghai"
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        now = datetime.now().astimezone()
        timezone_name = now.tzinfo.key if getattr(now.tzinfo, "key", None) else timezone_name
        return LocalTimeContext(
            now=now,
            timezone_name=timezone_name,
            date_text=now.strftime("%Y年%m月%d日"),
            weekday_label=WEEKDAY_LABELS[now.weekday()],
        )

    now = datetime.now(timezone)
    return LocalTimeContext(
        now=now,
        timezone_name=timezone_name,
        date_text=now.strftime("%Y年%m月%d日"),
        weekday_label=WEEKDAY_LABELS[now.weekday()],
    )


def build_date_artifact(title: str = "今天") -> DateArtifact:
    """构造日期卡片 artifact。

    使用缓存的原因不是为了性能，而是为了让测试和同一次请求里重复取值时保持一致。
    """
    context = get_local_time_context()
    return DateArtifact(
        data=DateArtifactData(
            title=title,
            date_text=context.date_text,
            weekday_label=context.weekday_label,
            timezone=context.timezone_name,
        )
    )
