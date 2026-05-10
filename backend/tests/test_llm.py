"""LLM 工厂测试。"""

from __future__ import annotations

from types import SimpleNamespace

import app.core.llm as llm_module


def _openai_settings(**overrides) -> SimpleNamespace:
    base = dict(
        active_llm_provider="openai",
        openai_enabled=True,
        openai_api_key="sk-demo",
        openai_base_url="https://api.example.com/v1",
        openai_model="MiniMax-M2.7",
        anthropic_api_key="",
        anthropic_base_url="",
        anthropic_model="",
        has_embedding_model=False,
        openai_embedding_model="",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _anthropic_settings(**overrides) -> SimpleNamespace:
    base = dict(
        active_llm_provider="anthropic",
        openai_enabled=False,
        openai_api_key="",
        openai_base_url="",
        openai_model="",
        anthropic_api_key="sk-cp-demo",
        anthropic_base_url="https://api.minimaxi.com/anthropic",
        anthropic_model="MiniMax-M2.7",
        anthropic_thinking_budget=4000,
        anthropic_max_tokens=8192,
        anthropic_output_tokens=4096,
        has_embedding_model=False,
        openai_embedding_model="",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_get_chat_model_uses_openai_when_provider_is_openai(monkeypatch) -> None:
    """provider=openai 时应实例化 ChatOpenAI 并带上配置项。"""
    captured: dict[str, object] = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(llm_module, "ChatOpenAI", FakeChatOpenAI)
    monkeypatch.setattr(llm_module, "get_settings", _openai_settings)

    model = llm_module.get_chat_model(temperature=0.2, streaming=True, tags=["unit-test"])

    assert model is not None
    assert captured["api_key"] == "sk-demo"
    assert captured["base_url"] == "https://api.example.com/v1"
    assert captured["model"] == "MiniMax-M2.7"
    assert captured["streaming"] is True
    assert captured["tags"] == ["unit-test"]


def test_get_chat_model_uses_anthropic_when_provider_is_anthropic(monkeypatch) -> None:
    """provider=anthropic 时应实例化 ChatAnthropic 并把 base_url/model 带过去。"""
    captured: dict[str, object] = {}

    class FakeChatAnthropic:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(llm_module, "ChatAnthropic", FakeChatAnthropic)
    monkeypatch.setattr(llm_module, "get_settings", _anthropic_settings)

    model = llm_module.get_chat_model(temperature=0.3, streaming=False, tags=["t"])

    assert model is not None
    assert captured["api_key"] == "sk-cp-demo"
    assert captured["base_url"] == "https://api.minimaxi.com/anthropic"
    assert captured["model"] == "MiniMax-M2.7"
    assert captured["streaming"] is False
    # 默认 enable_thinking=False：thinking 字段不挂，但 max_tokens 必须设到
    # anthropic_output_tokens 基线，避免落到 langchain-anthropic 默认 1024 把长文截断。
    assert "thinking" not in captured
    assert captured["max_tokens"] == 4096


def test_get_chat_model_enables_thinking_for_anthropic(monkeypatch) -> None:
    """enable_thinking=True 且 budget>0 时，应挂 thinking dict、强制 temperature=1、设 max_tokens。"""
    captured: dict[str, object] = {}

    class FakeChatAnthropic:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(llm_module, "ChatAnthropic", FakeChatAnthropic)
    monkeypatch.setattr(llm_module, "get_settings", _anthropic_settings)

    model = llm_module.get_chat_model(
        temperature=0.2,
        streaming=True,
        tags=["final_response"],
        enable_thinking=True,
    )

    assert model is not None
    assert captured["thinking"] == {"type": "enabled", "budget_tokens": 4000}
    # Anthropic 要求开 thinking 时 temperature 强制为 1，覆盖调用方传的 0.2
    assert captured["temperature"] == 1.0
    # max_tokens 必须 > budget，且至少给答案留 2048 tokens 余地
    assert captured["max_tokens"] >= 4000 + 2048


def test_get_chat_model_skips_thinking_when_budget_zero(monkeypatch) -> None:
    """全局 budget=0 时，即使 enable_thinking=True 也不该挂 thinking（供供应商不支持时一键关闭）。"""
    captured: dict[str, object] = {}

    class FakeChatAnthropic:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(llm_module, "ChatAnthropic", FakeChatAnthropic)
    monkeypatch.setattr(
        llm_module,
        "get_settings",
        lambda: _anthropic_settings(anthropic_thinking_budget=0),
    )

    llm_module.get_chat_model(enable_thinking=True)

    # budget=0 时不挂 thinking，但 max_tokens 仍按 output_tokens 基线设置
    assert "thinking" not in captured
    assert captured["max_tokens"] == 4096


def test_get_chat_model_returns_none_when_no_provider(monkeypatch) -> None:
    """既没配 OpenAI key 也没配 Anthropic key 时应返回 None。"""
    monkeypatch.setattr(
        llm_module,
        "get_settings",
        lambda: SimpleNamespace(active_llm_provider=""),
    )
    assert llm_module.get_chat_model() is None


def test_get_embeddings_model_returns_none_when_embedding_model_is_blank(monkeypatch) -> None:
    """未配置 Embedding 模型时应直接回退，不强行初始化远端向量模型。"""
    monkeypatch.setattr(llm_module, "get_settings", _openai_settings)

    model = llm_module.get_embeddings_model()

    assert model is None
