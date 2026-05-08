"""个人信息查询工具。"""

from __future__ import annotations

from functools import lru_cache

from langchain_core.tools import Tool

from app.core.security import CurrentUser
from app.services.personal_info_service import get_personal_info_service


def _lookup_personal_info(payload: str) -> str:
    """根据用户 ID 查询个人信息。"""
    current_user_id, target_user_id = payload.split("|", maxsplit=1)
    current_user = CurrentUser(
        sub=current_user_id,
        username="tool-user",
        name="tool-user",
        role="hr_admin",
        department="HR",
    )
    result = get_personal_info_service().get_personal_info(current_user, target_user_id)
    return str(result)


@lru_cache
def get_personal_info_tool() -> Tool:
    """返回个人信息工具。"""
    return Tool(
        name="personal_info_tool",
        description="根据员工 ID 查询个人信息。",
        func=_lookup_personal_info,
    )
