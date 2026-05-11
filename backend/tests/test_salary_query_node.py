"""薪酬查询节点测试。"""

from __future__ import annotations

import asyncio

import app.nodes.salary_query_node as salary_module
from app.core.security import CurrentUser
from app.nodes.salary_query_node import salary_query_node


def test_salary_query_node_does_not_initialize_llm() -> None:
    """薪酬查询已有结构化 service，不应启动 SQL Agent 或 LLM。"""
    assert not hasattr(salary_module, "get_chat_model")
    assert not hasattr(salary_module, "create_sql_agent")

    result = asyncio.run(
        salary_query_node(
            {
                "current_user": CurrentUser(
                    sub="u-1001",
                    username="li.wei",
                    name="李伟",
                    role="employee",
                    department="Finance",
                ),
                "target_user_id": "u-1001",
            }
        )
    )

    assert result["structured_data"]["payroll_month"] == "2026-04"
    assert result["structured_data"]["total_package"] == 23200
    assert "sql_result" in result["structured_data"]
