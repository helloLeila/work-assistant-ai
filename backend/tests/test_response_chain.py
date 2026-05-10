"""回答生成链测试。"""

from __future__ import annotations

from app.chains.response_chain import (
    detect_length_request,
    format_style_clause,
    length_target_clause,
    should_enable_extended_thinking,
)


def test_chitchat_response_uses_fast_generation_mode() -> None:
    """闲聊/写作类最终回答不应默认开启 extended thinking。"""
    assert should_enable_extended_thinking("chitchat") is False


def test_business_response_can_use_extended_thinking() -> None:
    """业务上下文回答仍可保留 extended thinking 能力。"""
    assert should_enable_extended_thinking("knowledge") is True


# ===== 输出格式风格 =====


def test_format_style_clause_for_business_intents_allows_markdown() -> None:
    """业务类 intent 的格式子句应允许 markdown。"""
    for intent in ("knowledge", "salary", "personal", "travel"):
        clause = format_style_clause(intent)
        assert "markdown" in clause
        assert "不要使用" not in clause, f"{intent} 不应禁止 markdown"


def test_format_style_clause_for_writing_forbids_markdown() -> None:
    """写作/闲聊类格式子句必须明确禁止 markdown 语法。"""
    clause = format_style_clause("chitchat")
    # 关键词检查：明确禁止 + 列出常见 markdown 语法
    assert "不要使用" in clause
    assert "##" in clause
    assert "**" in clause
    assert "散文" in clause


# ===== 长度要求解析 =====


def test_detect_length_request_returns_none_when_no_number() -> None:
    """没有'X 字'要求时返回 None。"""
    assert detect_length_request("帮我写一段开场白") is None
    assert detect_length_request("差旅报销最多能报多少") is None


def test_detect_length_request_extracts_number_with_unit() -> None:
    """识别'1000字'/'500 字'两种常见格式。"""
    assert detect_length_request("生成1000字面经") == 1000
    assert detect_length_request("写一篇 500 字的总结") == 500


def test_detect_length_request_takes_last_match() -> None:
    """用户多次提到字数时，以最后一次为准（视为用户的修正意图）。"""
    assert detect_length_request("先来 200 字……不对，给我 1500 字") == 1500


def test_detect_length_request_filters_out_of_range() -> None:
    """1 位数和 6 位以上数字视为误匹配，返回 None。"""
    assert detect_length_request("1 字概括") is None  # 太短，正则不会命中
    assert detect_length_request("写 100000 字") is None  # 超出 max_tokens 上限


# ===== 长度子句拼接 =====


def test_length_target_clause_returns_empty_when_no_target() -> None:
    """无目标字数时返回空字符串，保持原 prompt 行为。"""
    assert length_target_clause(None) == ""


def test_length_target_clause_includes_target_and_lower_bound() -> None:
    """长度子句必须同时给出目标值与 90% 下限，应对模型低估字数的天性。"""
    clause = length_target_clause(1000)
    assert "1000 字" in clause
    # 90% 下限 = 900
    assert "900" in clause
    # 鼓励大纲展开
    assert "大纲" in clause
