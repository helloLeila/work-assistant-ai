"""配置对象测试。

这些测试验证两件事：
1. 没有 backend/.env 时，项目也能用合理默认值启动；
2. 有 backend/.env 时，它要比外层 shell 环境变量更优先，避免本地开发混乱。
"""

from app.core.config import BACKEND_ROOT, Settings
from pathlib import Path


def test_settings_use_expected_defaults(monkeypatch) -> None:
    """默认配置应该匹配本地开发环境约定。"""
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_EMBEDDING_MODEL", raising=False)
    settings = Settings(_env_file=None)

    assert settings.app_name == "企业智能办公助手"
    assert settings.api_prefix == "/api"
    assert settings.frontend_url == "http://localhost:5173"
    assert settings.openai_base_url == ""
    assert settings.openai_embedding_model == "text-embedding-3-small"


def test_backend_env_file_path_is_fixed() -> None:
    """后端正式配置源应该固定在 backend/.env。"""
    assert Path(Settings.model_config["env_file"]) == BACKEND_ROOT / ".env"


def test_dotenv_should_override_outer_shell_env(tmp_path, monkeypatch) -> None:
    """backend/.env 应该覆盖外层 shell 里残留的同名变量。"""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "OPENAI_BASE_URL=https://file.example.com/v1\n"
        "OPENAI_MODEL=from-file-model\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENAI_BASE_URL", "https://shell.example.com/v1")
    monkeypatch.setenv("OPENAI_MODEL", "from-shell-model")

    settings = Settings(_env_file=env_file)

    assert settings.openai_base_url == "https://file.example.com/v1"
    assert settings.openai_model == "from-file-model"
