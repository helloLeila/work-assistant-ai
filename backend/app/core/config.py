"""应用配置。"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = PROJECT_ROOT / "backend"
DATA_ROOT = BACKEND_ROOT / "data"


class Settings(BaseSettings):
    """项目配置对象。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "企业智能办公助手"
    app_version: str = "1.0.0"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    api_prefix: str = "/api"
    frontend_url: str = "http://localhost:5173"
    public_api_base_url: str = "http://localhost:8000/api"
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )

    # ===== LLM 提供方配置 =====
    # 可选值：openai / anthropic
    # - openai：走 OpenAI 协议（OpenAI 官方 / MiniMax 按量计费 / 任何 OpenAI 兼容网关）
    # - anthropic：走 Anthropic 协议（Claude 官方 / MiniMax Token Plan / Coding Plan 等订阅 key）
    # 留空时按 anthropic_api_key / openai_api_key 是否填写自动判断。
    llm_provider: str = ""

    # OpenAI / OpenAI 兼容配置（pay-as-you-go 类 key 走这里）
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = "gpt-4o"
    # 如果当前供应商没有可用的 Embedding 接口，可以留空，系统会自动回退到本地词法检索。
    openai_embedding_model: str = "text-embedding-3-small"

    # Anthropic / Anthropic 兼容配置（MiniMax Token Plan / Coding Plan 的 sk-cp- key 走这里）
    anthropic_api_key: str = ""
    anthropic_base_url: str = ""
    anthropic_model: str = "claude-3-5-sonnet-latest"
    # 推理模型（Claude 3.7+ extended thinking / MiniMax M2.x）的思考预算 token 数。
    # 0 = 禁用，不让模型走 thinking 通道；>0 = 开启并允许模型最多消耗这么多 token 在内部推理上。
    # 仅对生成最终答案的链路生效，意图分类/抽取等需要确定性输出的小链路始终关闭。
    anthropic_thinking_budget: int = 4000
    # 开启 thinking 时单次响应的最大 token 上限（thinking + 答案 总额度）。
    # 必须严格 > anthropic_thinking_budget，给正式答案留空间。
    anthropic_max_tokens: int = 8192
    # 关闭 thinking 时纯答案的输出预算。中文 ~1.5 字/token，4096 tokens ≈ 2700 字，
    # 留够长文写作场景。如果用户经常要求 5000 字以上长文，把这个值开到 8192。
    # 历史背景：langchain-anthropic 默认 max_tokens=1024（≈ 700 中文字），
    # 经常导致"用户要 1000 字、模型只产 500-700 字"的截断。详见
    # docs/agent-design/03-output-format-and-length.md。
    anthropic_output_tokens: int = 4096

    langsmith_tracing_v2: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "ruirui-office-assistant"
    langsmith_endpoint: str = "https://api.smith.langchain.com"

    jwt_secret_key: str = "ruirui-access-secret"
    jwt_refresh_secret_key: str = "ruirui-refresh-secret"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 120
    refresh_token_expire_days: int = 7

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "ruirui"
    postgres_user: str = "ruirui"
    postgres_password: str = "ruirui"
    business_db_backend: str = "auto"
    postgres_connect_timeout_seconds: int = 2

    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = ""

    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_user: str = ""
    milvus_password: str = ""
    milvus_secure: bool = False
    milvus_collection_name: str = "enterprise_knowledge"

    default_department: str = "HR"
    knowledge_top_k: int = 5
    intent_confidence_threshold: float = 0.7
    llm_relevance_threshold: float = 0.6
    max_retry_count: int = 3
    travel_api_base_url: str = ""
    travel_api_path: str = "/orders"
    travel_api_auth_token: str = ""
    travel_api_timeout_seconds: float = 10.0
    travel_api_fallback_enabled: bool = True

    upload_dir: Path = DATA_ROOT / "uploads"
    knowledge_index_dir: Path = DATA_ROOT / "knowledge_index"
    knowledge_seed_dir: Path = DATA_ROOT / "seed_docs"
    knowledge_metadata_path: Path = DATA_ROOT / "knowledge_metadata.json"
    chat_history_path: Path = DATA_ROOT / "chat_history.json"
    business_db_path: Path = DATA_ROOT / "business_demo.db"

    @property
    def business_database_url(self) -> str:
        """返回供 SQLDatabase 使用的本地数据库地址。"""
        return f"sqlite:///{self.business_db_path}"

    @property
    def postgres_database_url(self) -> str:
        """返回 PostgreSQL 连接地址。"""
        user = quote_plus(self.postgres_user)
        password = quote_plus(self.postgres_password)
        return f"postgresql+psycopg://{user}:{password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    @property
    def openai_enabled(self) -> bool:
        """是否启用真实 OpenAI 模型。"""
        return bool(self.openai_api_key.strip())

    @property
    def anthropic_enabled(self) -> bool:
        """是否配置了 Anthropic / Anthropic 兼容 key。"""
        return bool(self.anthropic_api_key.strip())

    @property
    def active_llm_provider(self) -> str:
        """选择当前生效的聊天模型提供方。

        优先级：
        1. 如果 LLM_PROVIDER 显式指定为 openai / anthropic，则尊重显式配置；
        2. 否则按是否填写了对应 key 自动判断（Anthropic 优先于 OpenAI，因为
           大多数同时配置两套 key 的场景是 Anthropic 走主链路）；
        3. 都没配置则返回 ''，上层据此走 fallback。
        """
        explicit = self.llm_provider.strip().lower()
        if explicit in {"openai", "anthropic"}:
            return explicit
        if self.anthropic_enabled:
            return "anthropic"
        if self.openai_enabled:
            return "openai"
        return ""

    @property
    def llm_enabled(self) -> bool:
        """是否至少有一种聊天模型可用。"""
        return self.active_llm_provider != ""

    @property
    def has_embedding_model(self) -> bool:
        """是否配置了可用的 Embedding 模型名。"""
        return bool(self.openai_embedding_model.strip())

    @property
    def normalized_business_db_backend(self) -> str:
        """标准化结构化数据后端类型。"""
        value = self.business_db_backend.strip().lower()
        if value in {"sqlite", "postgres", "auto"}:
            return value
        return "auto"

    def ensure_directories(self) -> None:
        """确保运行目录存在。"""
        DATA_ROOT.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.knowledge_index_dir.mkdir(parents=True, exist_ok=True)
        self.knowledge_seed_dir.mkdir(parents=True, exist_ok=True)

    def apply_runtime_env(self) -> None:
        """把 LangSmith 相关配置同步到运行时环境。"""
        if self.langsmith_tracing_v2:
            os.environ["LANGCHAIN_TRACING_V2"] = "true"
        if self.langsmith_api_key:
            os.environ["LANGCHAIN_API_KEY"] = self.langsmith_api_key
        if self.langsmith_project:
            os.environ["LANGCHAIN_PROJECT"] = self.langsmith_project
        if self.langsmith_endpoint:
            os.environ["LANGCHAIN_ENDPOINT"] = self.langsmith_endpoint


@lru_cache
def get_settings() -> Settings:
    """缓存配置对象，避免重复解析环境变量。"""
    settings = Settings()
    settings.ensure_directories()
    settings.apply_runtime_env()
    return settings
