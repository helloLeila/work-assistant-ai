"""敏感信息脱敏工具。"""

from __future__ import annotations


def mask_phone(phone: str) -> str:
    """手机号脱敏。"""
    if len(phone) < 7:
        return phone
    return f"{phone[:3]}****{phone[-4:]}"


def mask_id_card(id_card: str) -> str:
    """身份证号脱敏。"""
    if len(id_card) < 8:
        return id_card
    return f"{id_card[:3]}***********{id_card[-4:]}"


def mask_salary(data: dict[str, object], role: str) -> dict[str, object]:
    """按角色脱敏薪酬信息。"""
    if role == "hr_admin":
        return data
    if role == "manager":
        return {
            **data,
            "tax": "受限",
            "social_security": "受限",
        }
    return {
        "payroll_month": data.get("payroll_month"),
        "total_package": data.get("total_package"),
        "base_salary": "受限",
        "bonus": "受限",
        "allowance": "受限",
        "tax": "受限",
        "social_security": "受限",
    }
