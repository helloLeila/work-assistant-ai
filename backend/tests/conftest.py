"""测试环境统一设置。"""

from __future__ import annotations

import os

import pytest

from app.core.config import get_settings

# 单元测试默认不读取开发者本机的 backend/.env，避免真实 key / 私有配置污染测试结果。
os.environ.setdefault("TONGTONG_TESTING", "1")

TEST_ISOLATED_ENV_KEYS = [
    "LLM_PROVIDER",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_MODEL",
    "OPENAI_UTILITY_MODEL",
    "OPENAI_EMBEDDING_MODEL",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_MODEL",
    "ANTHROPIC_UTILITY_MODEL",
    "ANTHROPIC_THINKING_BUDGET",
    "ANTHROPIC_MAX_TOKENS",
    "ANTHROPIC_OUTPUT_TOKENS",
    "TRAVEL_API_BASE_URL",
    "TRAVEL_API_PATH",
    "TRAVEL_API_AUTH_TOKEN",
    "BOCHA_API_KEY",
    "BOCHA_BASE_URL",
]


@pytest.fixture(autouse=True)
def clear_settings_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """每个测试前后都隔离运行时环境，保证 monkeypatch 立即生效。"""
    for key in TEST_ISOLATED_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
