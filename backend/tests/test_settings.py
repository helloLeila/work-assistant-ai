"""配置对象测试。

这个测试保证项目在没有 .env 的情况下，
也能用合理默认值启动开发环境。
"""

from app.core.config import Settings


def test_settings_use_expected_defaults(monkeypatch) -> None:
    """默认配置应该匹配本地开发环境约定。"""
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_EMBEDDING_MODEL", raising=False)
    settings = Settings()

    assert settings.app_name == "企业智能办公助手"
    assert settings.api_prefix == "/api"
    assert settings.frontend_url == "http://localhost:5173"
    assert settings.openai_base_url == ""
    assert settings.openai_embedding_model == "text-embedding-3-small"
