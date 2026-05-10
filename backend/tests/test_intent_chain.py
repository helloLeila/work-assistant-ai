"""意图分类链测试。"""

from __future__ import annotations

import asyncio

import app.chains.intent_chain as intent_chain


def test_obvious_business_intent_uses_local_fast_path(monkeypatch) -> None:
    """明显业务意图应走本地快速路径，不等待远端 LLM。"""

    def fail_if_llm_is_used(*args, **kwargs):
        raise AssertionError("obvious intent should not initialize the LLM")

    monkeypatch.setattr(intent_chain, "get_utility_chat_model", fail_if_llm_is_used)

    result = asyncio.run(intent_chain.classify_intent("请查询我本月的薪酬总包"))

    assert result.intent == "salary"
    assert result.confidence >= 0.9
    assert "本地快速" in result.reason


def test_generation_request_uses_local_chitchat_fast_path(monkeypatch) -> None:
    """写作/生成类请求应直接进入通用生成，不等待意图 LLM。"""

    def fail_if_llm_is_used(*args, **kwargs):
        raise AssertionError("generation request should not initialize the LLM")

    monkeypatch.setattr(intent_chain, "get_utility_chat_model", fail_if_llm_is_used)

    result = asyncio.run(intent_chain.classify_intent("生成200字面试经验agent方向"))

    assert result.intent == "chitchat"
    assert result.confidence >= 0.9
    assert "本地快速" in result.reason


def test_identity_question_uses_chitchat_fast_path(monkeypatch) -> None:
    """'你是谁' / '你好' 这类问候必须走 fast-path,不能让意图分类等大模型。"""

    def fail_if_llm_is_used(*args, **kwargs):
        raise AssertionError("greeting should not initialize the LLM")

    monkeypatch.setattr(intent_chain, "get_utility_chat_model", fail_if_llm_is_used)

    for greeting in ("你是谁", "你好", "您好", "hi", "hello", "你能做什么", "谢谢"):
        result = asyncio.run(intent_chain.classify_intent(greeting))
        assert result.intent == "chitchat", greeting
        assert "本地快速" in result.reason


def test_short_query_falls_back_to_chitchat(monkeypatch) -> None:
    """≤15 字 + 无业务关键词的零碎短文本(在吗/嗯/ok)默认 chitchat,不调 LLM。"""

    def fail_if_llm_is_used(*args, **kwargs):
        raise AssertionError("short query should not initialize the LLM")

    monkeypatch.setattr(intent_chain, "get_utility_chat_model", fail_if_llm_is_used)

    # 故意挑没在 KEYWORD_RULES 里的短文本,验证第二层兜底
    for short in ("在吗", "嗯", "ok", "在不在", "?"):
        result = asyncio.run(intent_chain.classify_intent(short))
        assert result.intent == "chitchat", short
        # confidence 0.85 = 短查询兜底,与显式关键词命中(0.93)分级
        assert result.confidence == 0.85
        assert "短查询" in result.reason


def test_long_business_query_does_not_hit_short_fallback(monkeypatch) -> None:
    """长 query 即使没业务关键词也不应被短查询兜底吃掉,要正常走 LLM 分类。

    用 sentinel 让 LLM 调用立即抛错,验证流程进到了第三层。
    """
    sentinel = AssertionError("expected: reached LLM tier")

    def trip(*args, **kwargs):
        raise sentinel

    monkeypatch.setattr(intent_chain, "get_utility_chat_model", trip)

    long_ambiguous = "我想问一下关于上个月那个事情的进展现在到哪一步了"
    try:
        asyncio.run(intent_chain.classify_intent(long_ambiguous))
    except AssertionError as exc:
        assert exc is sentinel
    else:
        raise AssertionError("long ambiguous query should have reached the LLM tier")
