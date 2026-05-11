"""结构化抽取链快路径测试。"""

from __future__ import annotations

import asyncio

import app.chains.extraction_chain as extraction_chain


def test_personal_query_uses_local_keywords_before_llm(monkeypatch) -> None:
    """年假/合同等固定字段抽取应本地完成，不等待 LLM parser。"""

    def fail_if_llm_is_used(*args, **kwargs):
        raise AssertionError("personal field extraction should use local keywords first")

    monkeypatch.setattr(extraction_chain, "get_utility_chat_model", fail_if_llm_is_used)

    result = asyncio.run(extraction_chain.extract_personal_query("帮我查看我的剩余年假"))

    assert result.requested_fields == ["annual_leave"]
