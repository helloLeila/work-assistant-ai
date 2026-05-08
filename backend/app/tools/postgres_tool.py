"""SQL 查询工具。"""

from __future__ import annotations

from functools import lru_cache

from langchain_community.tools.sql_database.tool import QuerySQLDatabaseTool

from app.services.business_db_service import get_business_database_service


@lru_cache
def get_query_sql_tool() -> QuerySQLDatabaseTool:
    """返回 LangChain SQL 查询工具。"""
    return QuerySQLDatabaseTool(db=get_business_database_service().sql_database)
