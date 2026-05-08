"""薪酬服务。"""

from __future__ import annotations

from functools import lru_cache

from app.core.security import CurrentUser
from app.models.domain import PermissionDecision
from app.services.business_db_service import get_business_database_service
from app.utils.masking import mask_salary


class PayrollService:
    """处理薪酬查询与权限校验。"""

    def __init__(self) -> None:
        self._db = get_business_database_service()

    def resolve_target_user_id(self, query: str, current_user: CurrentUser) -> str:
        """从查询中解析目标用户。"""
        employees = self._db.list_employees()
        for employee in employees:
            if str(employee["name"]) in query:
                return str(employee["user_id"])
        return current_user.user_id

    def authorize(self, current_user: CurrentUser, target_user_id: str) -> PermissionDecision:
        """判断薪酬查询权限。"""
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
            message="当前账号没有查看该薪酬记录的权限。",
        )

    def get_salary_summary(self, current_user: CurrentUser, target_user_id: str) -> dict[str, object]:
        """获取脱敏后的薪酬数据。"""
        raw = self._db.fetch_payroll_record(target_user_id)
        if raw is None:
            return {"message": "未找到对应的薪酬记录。"}
        return mask_salary(raw, role=current_user.role)

    def get_sql_for_user(self, target_user_id: str) -> str:
        """生成查询最近一期薪酬记录的 SQL。"""
        return (
            "SELECT user_id, payroll_month, base_salary, bonus, allowance, tax, social_security, total_package "
            "FROM payroll_records "
            f"WHERE user_id = '{target_user_id}' "
            "ORDER BY payroll_month DESC LIMIT 1"
        )


@lru_cache
def get_payroll_service() -> PayrollService:
    return PayrollService()


def get_payroll_module_snapshot() -> dict[str, str]:
    return {
        "name": "薪酬查询",
        "status": "已启用",
        "highlight": "支持角色权限控制和薪酬字段脱敏",
        "capability": "员工查自己，经理查直属下属，HR 可看完整明细",
    }
