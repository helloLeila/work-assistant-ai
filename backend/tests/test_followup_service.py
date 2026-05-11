"""上下文追问快路径测试。"""

from __future__ import annotations

from app.services.followup_service import answer_contextual_followup


def test_salary_limited_followup_returns_direct_answer() -> None:
    """用户追问“受限”时，应基于上一轮薪酬上下文直接解释权限脱敏。"""
    answer = answer_contextual_followup(
        query="受限怎么回事",
        recent_assistant_content="你最近一期（2026-04）的薪酬信息：总包 23200 元，基本工资 受限，奖金 受限。",
    )

    assert answer is not None
    assert "受限" in answer
    assert "权限" in answer
    assert "脱敏" in answer


def test_unrelated_short_query_does_not_match_salary_followup() -> None:
    """没有薪酬上下文时，短句追问不应被薪酬解释误吃掉。"""
    answer = answer_contextual_followup(
        query="怎么回事",
        recent_assistant_content="我是企业智能办公助手，可以帮你查询公司制度。",
    )

    assert answer is None
