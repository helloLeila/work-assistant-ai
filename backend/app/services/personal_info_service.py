"""个人信息服务。"""

from __future__ import annotations

from functools import lru_cache

from app.core.security import CurrentUser
from app.models.domain import PermissionDecision
from app.services.business_db_service import get_business_database_service
from app.utils.masking import mask_id_card, mask_phone


class PersonalInfoService:
    """处理个人信息查询。"""

    def __init__(self) -> None:
        self._db = get_business_database_service()

    def resolve_target_user_id(self, query: str, current_user: CurrentUser) -> str:
        """解析目标用户。"""
        employees = self._db.list_employees()
        for employee in employees:
            if str(employee["name"]) in query:
                return str(employee["user_id"])
        return current_user.user_id

    def authorize(self, current_user: CurrentUser, target_user_id: str) -> PermissionDecision:
        """判断个人信息查询权限。"""
        if current_user.role == "hr_admin":
            return PermissionDecision(allowed=True, target_user_id=target_user_id)
        if current_user.role == "employee" and current_user.user_id == target_user_id:
            return PermissionDecision(allowed=True, target_user_id=target_user_id)
        if current_user.role == "manager":
            direct_reports = self._db.fetch_direct_reports(current_user.user_id)
            if target_user_id == current_user.user_id or target_user_id in direct_reports:
                return PermissionDecision(allowed=True, target_user_id=target_user_id)
        return PermissionDecision(
            allowed=False,
            target_user_id=target_user_id,
            message="当前账号没有查看该员工个人信息的权限。",
        )

    def get_personal_info(self, current_user: CurrentUser, target_user_id: str) -> dict[str, object]:
        """返回按角色脱敏后的个人信息。"""
        employee = self._db.fetch_employee(target_user_id)
        if employee is None:
            return {"message": "未找到对应员工。"}

        if current_user.role == "hr_admin":
            return employee

        return {
            "user_id": employee["user_id"],
            "name": employee["name"],
            "department": employee["department"],
            "annual_leave": employee["annual_leave"],
            "contract_end": employee["contract_end"],
            "phone": mask_phone(str(employee["phone"])),
            "id_card": mask_id_card(str(employee["id_card"])),
        }


@lru_cache
def get_personal_info_service() -> PersonalInfoService:
    return PersonalInfoService()


def get_personal_module_snapshot() -> dict[str, str]:
    return {
        "name": "个人信息查询",
        "status": "已启用",
        "highlight": "支持手机号与身份证自动脱敏",
        "capability": "支持年假、合同、部门与基础信息查询",
    }
