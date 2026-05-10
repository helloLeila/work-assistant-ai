"""LLM 与 Embedding 工厂。

支持两类聊天协议：
1. OpenAI 协议（OpenAI 官方 / OpenAI 兼容网关 / MiniMax 按量计费）→ ChatOpenAI
2. Anthropic 协议（Claude 官方 / MiniMax Token Plan / Coding Plan）→ ChatAnthropic

具体由 settings.active_llm_provider 决定，调用方一律走 get_chat_model()，
不需要关心底层是哪种协议——LangChain 的 BaseChatModel 抽象层会兜住差异，
所以现有的 `prompt | llm | parser` 链路无需改动。
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _build_openai_client_kwargs() -> dict[str, Any]:
    """统一组装 OpenAI / OpenAI 兼容接口的公共参数。"""
    settings = get_settings()
    client_kwargs: dict[str, Any] = {
        "api_key": settings.openai_api_key,
    }

    # 只有在用户显式配置时才传 base_url，避免影响 OpenAI 官方默认地址。
    if settings.openai_base_url.strip():
        client_kwargs["base_url"] = settings.openai_base_url.strip()

    return client_kwargs


def _build_anthropic_client_kwargs() -> dict[str, Any]:
    """统一组装 Anthropic / Anthropic 兼容接口的公共参数。"""
    settings = get_settings()
    client_kwargs: dict[str, Any] = {
        "api_key": settings.anthropic_api_key,
    }
    if settings.anthropic_base_url.strip():
        # langchain-anthropic 用 base_url 参数（底层会传给 anthropic SDK）
        client_kwargs["base_url"] = settings.anthropic_base_url.strip()
    return client_kwargs


def get_chat_model(
    *,
    temperature: float = 0.1,
    streaming: bool = False,
    tags: Sequence[str] | None = None,
    enable_thinking: bool = False,
) -> BaseChatModel | None:
    """按配置创建聊天模型。

    返回类型用 BaseChatModel，因为底层可能是 ChatOpenAI 也可能是 ChatAnthropic，
    但调用侧只用到 LangChain 通用接口（astream / invoke / | 管道），不会感知差异。

    enable_thinking=True 时（仅 anthropic 协议有效）会开启 extended thinking：
    - 在请求里带 thinking={"type": "enabled", "budget_tokens": ...}
    - Anthropic 规范要求开启 thinking 时 temperature 必须为 1，会强制覆盖。
    - max_tokens 必须 > thinking_budget，否则模型直接报错。
    意图分类、grading、字段抽取等需要确定性 JSON 输出的链路务必保持默认 False，
    否则 budget_tokens 会被消耗在没用的"内省"上，反而降低稳定性。
    """
    settings = get_settings()
    provider = settings.active_llm_provider
    if not provider:
        return None

    tag_list = list(tags or [])

    try:
        if provider == "anthropic":
            anthropic_kwargs: dict[str, Any] = {
                **_build_anthropic_client_kwargs(),
                "model": settings.anthropic_model,
                "temperature": temperature,
                "streaming": streaming,
                "tags": tag_list,
                # 永远显式设 max_tokens，避免 langchain-anthropic 默认 1024 把长文截断。
                # 默认走"非 thinking 输出预算"基线；thinking 模式下面会再覆盖一次。
                "max_tokens": settings.anthropic_output_tokens,
            }
            # 仅在调用方显式打开、且全局 budget>0 时才挂 thinking 参数；
            # 这样关掉 budget（=0）也能等同于完全禁用 thinking，对供应商友好。
            if enable_thinking and settings.anthropic_thinking_budget > 0:
                anthropic_kwargs["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": settings.anthropic_thinking_budget,
                }
                # Anthropic 协议要求开 thinking 时 temperature=1，否则会 400。
                anthropic_kwargs["temperature"] = 1.0
                # max_tokens 必须严格大于 thinking_budget，预留答案 token 空间。
                # 取 (配置, budget+2048) 中较大者，确保答案至少有 2k token 余地。
                anthropic_kwargs["max_tokens"] = max(
                    settings.anthropic_max_tokens,
                    settings.anthropic_thinking_budget + 2048,
                )
            return ChatAnthropic(**anthropic_kwargs)
        # 默认走 OpenAI 协议
        return ChatOpenAI(
            **_build_openai_client_kwargs(),
            model=settings.openai_model,
            temperature=temperature,
            streaming=streaming,
            tags=tag_list,
        )
    except Exception as exc:
        # 不要静默吞掉异常——SOCKS 代理 / 网络问题 / API key 失效都可能从这里冒出来。
        # 打 ERROR 日志后再返回 None，让上层 fallback 时至少能在日志里看到原因。
        logger.error("聊天模型初始化失败（provider=%s）：%s", provider, exc, exc_info=True)
        return None


def get_utility_chat_model(
    *,
    temperature: float = 0,
    tags: Sequence[str] | None = None,
) -> BaseChatModel | None:
    """轻量 utility 模型工厂——专给意图分类 / grading / 字段抽取 / 大纲规划用。

    设计动机详见 docs/agent-design/02-routing-and-model-tiers.md：
    - 这些链路是"高频 + 短输出 + 要确定性"的小调用，本不需要顶配推理模型；
    - 主模型(Claude Coding Plan / Claude Sonnet)开 thinking 后单次 ~25s，
      用在意图分类上等于让用户每次都先等一个"思考下你想干啥"的开销。
    - 切到 utility tier(gpt-4o-mini / haiku 等)单次 ~1-2s，体感立刻顺。

    与 get_chat_model() 的差异：
    1. 永不开 thinking，永不流式(utility 链路都是 ainvoke 一次拿 JSON/dict)。
    2. 默认 temperature=0(分类/抽取要稳定)。
    3. 用 *_utility_model 配置;留空时回退到主模型——保留向后兼容。
    """
    settings = get_settings()
    provider = settings.active_llm_provider
    if not provider:
        return None

    tag_list = list(tags or [])

    try:
        if provider == "anthropic":
            # Anthropic 协议侧若没单独配 utility 模型则回退到主模型;
            # 至少不会因为切 tier 反而把已有部署搞崩。
            model_name = settings.anthropic_utility_model.strip() or settings.anthropic_model
            return ChatAnthropic(
                **_build_anthropic_client_kwargs(),
                model=model_name,
                temperature=temperature,
                streaming=False,
                tags=tag_list,
                # utility 链路输出短(分类 JSON / 大纲 < 200 字),给 1024 足够,
                # 同时也避免主模型那套 8k max_tokens 拖慢 stop 判定。
                max_tokens=1024,
            )
        # OpenAI / OpenAI 兼容
        model_name = settings.openai_utility_model.strip() or settings.openai_model
        return ChatOpenAI(
            **_build_openai_client_kwargs(),
            model=model_name,
            temperature=temperature,
            streaming=False,
            tags=tag_list,
        )
    except Exception as exc:
        logger.error("utility 模型初始化失败（provider=%s）：%s", provider, exc, exc_info=True)
        return None


def get_embeddings_model() -> OpenAIEmbeddings | None:
    """按配置创建 Embedding 模型。

    Embedding 目前只支持 OpenAI 协议——MiniMax Token Plan 不提供向量化接口。
    如果当前供应商只有聊天模型，就把 OPENAI_EMBEDDING_MODEL 留空，
    系统会自动回退到本地词法检索。
    """
    settings = get_settings()
    if not settings.openai_enabled or not settings.has_embedding_model:
        return None
    try:
        return OpenAIEmbeddings(
            **_build_openai_client_kwargs(),
            model=settings.openai_embedding_model,
        )
    except Exception as exc:
        logger.error("OpenAIEmbeddings 初始化失败：%s", exc, exc_info=True)
        return None
