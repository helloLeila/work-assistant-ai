"""日志配置。"""

from __future__ import annotations

import logging
import re

PHONE_PATTERN = re.compile(r"1\d{10}")
ID_CARD_PATTERN = re.compile(r"\b\d{17}[\dXx]\b")
MONEY_PATTERN = re.compile(r"(?<!\d)(\d{4,6})(?!\d)")


def redact_sensitive_text(message: str) -> str:
    """对敏感数据做统一脱敏。"""
    redacted = PHONE_PATTERN.sub(lambda match: f"{match.group(0)[:3]}****{match.group(0)[-4:]}", message)
    redacted = ID_CARD_PATTERN.sub(
        lambda match: f"{match.group(0)[:3]}***********{match.group(0)[-4:]}",
        redacted,
    )
    redacted = MONEY_PATTERN.sub(lambda match: f"{match.group(0)[:2]}***", redacted)
    return redacted


class RedactingFilter(logging.Filter):
    """对日志消息做简单脱敏。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_sensitive_text(str(record.getMessage()))
        record.args = ()
        return True


def configure_logging() -> None:
    """配置全局日志格式。"""
    root_logger = logging.getLogger()
    if root_logger.handlers:
        return

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    root_logger.addFilter(RedactingFilter())
