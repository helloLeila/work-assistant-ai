"""planner_chain 单测:触发门槛 + 无 LLM 时的兜底。"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from app.chains.planner_chain import (
    PLANNER_MIN_TARGET_CHARS,
    plan_writing_outline,
    should_run_planner,
)


class TestShouldRunPlanner:
    def test_non_chitchat_never_plans(self):
        # 业务类(knowledge/salary/...)本来就走结构化数据,不需要大纲
        assert should_run_planner(intent="knowledge", target_chars=2000) is False
        assert should_run_planner(intent="salary", target_chars=1000) is False

    def test_chitchat_without_target_no_plan(self):
        # 用户没写"X字",一气呵成更快
        assert should_run_planner(intent="chitchat", target_chars=None) is False

    def test_chitchat_below_threshold_no_plan(self):
        # 低于 500 字门槛,大纲反而是开销
        assert should_run_planner(intent="chitchat", target_chars=PLANNER_MIN_TARGET_CHARS - 1) is False
        assert should_run_planner(intent="chitchat", target_chars=200) is False

    def test_chitchat_at_threshold_plans(self):
        # 边界条件:刚好等于门槛也要规划
        assert should_run_planner(intent="chitchat", target_chars=PLANNER_MIN_TARGET_CHARS) is True

    def test_chitchat_long_plans(self):
        assert should_run_planner(intent="chitchat", target_chars=1000) is True
        assert should_run_planner(intent="chitchat", target_chars=5000) is True


class TestPlanWritingOutline:
    def test_no_llm_returns_empty_string(self):
        # LLM 不可用时返回空串,调用方会回退到无大纲生成(向后兼容)
        with patch("app.chains.planner_chain.get_chat_model", return_value=None):
            result = asyncio.run(plan_writing_outline("写 1000 字面试经验", 1000))
        assert result == ""
