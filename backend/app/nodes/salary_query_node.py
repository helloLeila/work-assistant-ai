"""薪酬查询节点。"""

from __future__ import annotations

from langchain_community.agent_toolkits import create_sql_agent

from app.core.llm import get_chat_model
from app.services.business_db_service import get_business_database_service
from app.services.payroll_service import get_payroll_service


async def salary_query_node(state: dict) -> dict:
    """执行薪酬查询。"""
    current_user = state["current_user"]
    target_user_id = state["target_user_id"]

    llm = get_chat_model(temperature=0, tags=["salary_sql"])
    db_service = get_business_database_service()
    payroll_service = get_payroll_service()
    sql = payroll_service.get_sql_for_user(target_user_id)

    if llm is not None:
        agent = create_sql_agent(
            llm,
            db=db_service.sql_database,
            agent_type="tool-calling",
            verbose=False,
            max_iterations=4,
        )
        agent_input = f"请查询用户 {target_user_id} 最近一期薪酬记录，并返回结构化结果。"
        agent_result = await agent.ainvoke({"input": agent_input})
        sql_answer = agent_result.get("output")
    else:
        sql_answer = db_service.execute_sql(sql)

    structured_data = payroll_service.get_salary_summary(current_user, target_user_id)
    structured_data["sql_result"] = sql_answer
    return {"structured_data": structured_data}
