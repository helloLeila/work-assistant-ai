"""业务数据库服务。"""

from __future__ import annotations

from functools import lru_cache

from langchain_community.tools.sql_database.tool import QuerySQLDatabaseTool
from langchain_community.utilities import SQLDatabase
from sqlalchemy import Engine, text

from app.core.config import get_settings
from app.core.database import build_database_engine, ensure_business_database, ensure_postgres_business_database


class BusinessDatabaseService:
    """封装结构化业务数据库，优先使用 PostgreSQL。"""

    def __init__(self) -> None:
        self._settings = get_settings()
        # 无论最终是否走 PostgreSQL，本地样例库都会先准备好，
        # 这样当外部数据库不可用时，系统仍然能继续运行。
        ensure_business_database()
        self._backend, database_url = self._resolve_database_url()
        self._engine = build_database_engine(database_url)
        # SQLDatabase 主要给 LangChain 的 SQL Tool 和 SQL Agent 使用。
        self._sql_database = SQLDatabase.from_uri(database_url)
        self._query_tool = QuerySQLDatabaseTool(db=self._sql_database)

    @property
    def sql_database(self) -> SQLDatabase:
        return self._sql_database

    @property
    def backend_name(self) -> str:
        """当前使用的数据后端。"""
        return self._backend

    def execute_sql(self, sql: str) -> str:
        """通过 LangChain SQL 工具执行查询。"""
        return str(self._query_tool.invoke(sql))

    def fetch_employee(self, user_id: str) -> dict[str, object] | None:
        row = self._fetch_one("SELECT * FROM employees WHERE user_id = :user_id", {"user_id": user_id})
        return dict(row) if row else None

    def fetch_direct_reports(self, manager_id: str) -> list[str]:
        rows = self._fetch_all("SELECT user_id FROM employees WHERE manager_id = :manager_id", {"manager_id": manager_id})
        return [str(row["user_id"]) for row in rows]

    def fetch_payroll_record(self, user_id: str) -> dict[str, object] | None:
        row = self._fetch_one(
            """
            SELECT * FROM payroll_records
            WHERE user_id = :user_id
            ORDER BY payroll_month DESC
            LIMIT 1
            """,
            {"user_id": user_id},
        )
        return dict(row) if row else None

    def search_user_id_by_name(self, name: str) -> str | None:
        row = self._fetch_one("SELECT user_id FROM employees WHERE name = :name", {"name": name})
        return str(row["user_id"]) if row else None

    def list_employees(self) -> list[dict[str, object]]:
        rows = self._fetch_all("SELECT * FROM employees ORDER BY role, department")
        return [dict(row) for row in rows]

    def _resolve_database_url(self) -> tuple[str, str]:
        """根据配置选择结构化数据后端。"""
        backend = self._settings.normalized_business_db_backend
        if backend in {"auto", "postgres"}:
            try:
                # 只要 PostgreSQL 初始化成功，就优先走真实结构化数据库路径。
                ensure_postgres_business_database()
                return "postgres", self._settings.postgres_database_url
            except Exception:
                # auto 模式下，PostgreSQL 不可达时自动回退到 SQLite；
                # postgres 强制模式下则直接抛错，避免悄悄切换后端。
                if backend == "postgres":
                    raise
        return "sqlite", self._settings.business_database_url

    def _fetch_one(self, sql: str, params: dict[str, object] | None = None) -> dict[str, object] | None:
        """读取单行结果。"""
        with self._engine.begin() as connection:
            row = connection.execute(text(sql), params or {}).mappings().first()
        return dict(row) if row else None

    def _fetch_all(self, sql: str, params: dict[str, object] | None = None) -> list[dict[str, object]]:
        """读取多行结果。"""
        with self._engine.begin() as connection:
            rows = connection.execute(text(sql), params or {}).mappings().all()
        return [dict(row) for row in rows]


@lru_cache
def get_business_database_service() -> BusinessDatabaseService:
    return BusinessDatabaseService()
