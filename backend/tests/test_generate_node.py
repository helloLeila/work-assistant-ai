"""答案生成节点快路径测试。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import app.nodes.generate_node as generate_module
from app.nodes.generate_node import generate_node


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
