"""答案生成节点快路径测试。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import app.nodes.generate_node as generate_module
from app.nodes.generate_node import generate_node
from app.services.time_service import get_local_time_context


class FakeStreamer:
    def __init__(self) -> None:
        self.tokens: list[str] = []
        self.progress: list[tuple[str, str]] = []

    async def push_token(self, token: str) -> None:
        self.tokens.append(token)

    async def push_progress(self, *, step: str, detail: str) -> None:
        self.progress.append((step, detail))


def _runtime(streamer: FakeStreamer):
    return SimpleNamespace(context=SimpleNamespace(streamer=streamer))


def _expected_local_date() -> tuple[str, str]:
    context = get_local_time_context()
    return context.date_text, context.weekday_label


def test_identity_question_uses_direct_template(monkeypatch) -> None:
    """'你是谁' 这类固定意图必须模板直出，不调用最终 LLM。"""

    async def fail_if_llm_is_used(**kwargs):
        raise AssertionError("fixed identity response should not call stream_final_answer")

    monkeypatch.setattr(generate_module, "stream_final_answer", fail_if_llm_is_used)
    streamer = FakeStreamer()

    result = asyncio.run(
        generate_node(
            {
                "query": "你是谁",
                "intent": "chitchat",
            },
            _runtime(streamer),
        )
    )

    assert "企业智能办公助手" in result["final_answer"]
    assert "薪酬" in result["final_answer"]
    assert "".join(streamer.tokens) == result["final_answer"]


def test_personal_annual_leave_uses_structured_direct_answer(monkeypatch) -> None:
    """剩余年假等个人结构化数据应模板直出，不再等模型生成正文。"""

    async def fail_if_llm_is_used(**kwargs):
        raise AssertionError("personal structured answer should not call stream_final_answer")

    monkeypatch.setattr(generate_module, "stream_final_answer", fail_if_llm_is_used)
    streamer = FakeStreamer()

    result = asyncio.run(
        generate_node(
            {
                "query": "帮我查看我的剩余年假",
                "intent": "personal",
                "structured_data": {
                    "name": "李伟",
                    "annual_leave": 7,
                    "contract_end": "2026-12-31",
                },
            },
            _runtime(streamer),
        )
    )

    assert "李伟" in result["final_answer"]
    assert "剩余年假" in result["final_answer"]
    assert "7 天" in result["final_answer"]
    assert "".join(streamer.tokens) == result["final_answer"]


def test_current_date_question_uses_local_time_template(monkeypatch) -> None:
    """今天几号这类问题应直接返回本地日期，不走最终 LLM。"""

    async def fail_if_llm_is_used(**kwargs):
        raise AssertionError("date response should not call stream_final_answer")

    monkeypatch.setattr(generate_module, "stream_final_answer", fail_if_llm_is_used)
    streamer = FakeStreamer()

    result = asyncio.run(
        generate_node(
            {
                "query": "今天几号",
                "intent": "chitchat",
            },
            _runtime(streamer),
        )
    )

    date_text, weekday_label = _expected_local_date()
    assert date_text in result["final_answer"]
    assert weekday_label in result["final_answer"]
    assert "".join(streamer.tokens) == result["final_answer"]


def test_current_weekday_question_uses_local_time_template(monkeypatch) -> None:
    """今天星期几这类问题应直接返回本地星期，不走最终 LLM。"""

    async def fail_if_llm_is_used(**kwargs):
        raise AssertionError("weekday response should not call stream_final_answer")

    monkeypatch.setattr(generate_module, "stream_final_answer", fail_if_llm_is_used)
    streamer = FakeStreamer()

    result = asyncio.run(
        generate_node(
            {
                "query": "今天星期几",
                "intent": "chitchat",
            },
            _runtime(streamer),
        )
    )

    date_text, weekday_label = _expected_local_date()
    assert weekday_label in result["final_answer"]
    assert date_text in result["final_answer"]
    assert "".join(streamer.tokens) == result["final_answer"]


def test_current_date_question_emits_date_artifact(monkeypatch) -> None:
    """今天几号应同时产出日期卡片 artifact。"""

    async def fail_if_llm_is_used(**kwargs):
        raise AssertionError("date response should not call stream_final_answer")

    monkeypatch.setattr(generate_module, "stream_final_answer", fail_if_llm_is_used)
    streamer = FakeStreamer()

    result = asyncio.run(
        generate_node(
            {
                "query": "今天几号",
                "intent": "chitchat",
            },
            _runtime(streamer),
        )
    )

    date_text, _ = _expected_local_date()
    assert result["artifacts"][0]["kind"] == "date_card"
    assert result["artifacts"][0]["data"]["title"] == "今天"
    assert date_text in result["artifacts"][0]["data"]["date_text"]
