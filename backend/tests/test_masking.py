"""脱敏工具测试。"""

from app.utils.masking import mask_id_card, mask_phone, mask_salary


def test_mask_phone_and_id_card() -> None:
    """手机号和身份证号应按预期脱敏。"""
    assert mask_phone("13812345678") == "138****5678"
    assert mask_id_card("110101199001011234") == "110***********1234"


def test_mask_salary_for_employee() -> None:
    """普通员工看到薪酬时应隐藏不允许查看的字段。"""
    result = mask_salary(
        {
            "base_salary": 18000,
            "bonus": 4000,
            "allowance": 1200,
            "tax": 2600,
            "social_security": 900,
            "total_package": 23200,
        },
        role="employee",
    )

    assert result["total_package"] == 23200
    assert result["base_salary"] == "受限"
    assert result["bonus"] == "受限"
