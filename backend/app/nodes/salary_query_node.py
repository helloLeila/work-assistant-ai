"""薪酬查询节点。"""

from __future__ import annotations

from app.services.business_db_service import get_business_database_service
from app.services.payroll_service import get_payroll_service


async def salary_query_node(state: dict) -> dict:
    """执行薪酬查询。"""
    current_user = state["current_user"]
    target_user_id = state["target_user_id"]

    db_service = get_business_database_service()
    payroll_service = get_payroll_service()
    sql = payroll_service.get_sql_for_user(target_user_id)

    structured_data = payroll_service.get_salary_summary(current_user, target_user_id)
    structured_data["sql_result"] = db_service.execute_sql(sql)
    return {"structured_data": structured_data}
