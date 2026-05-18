"""知识接入服务。

处理文档上传、解析、切分、索引写入的完整流程，支持失败回滚与分步重试。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.config import get_settings
from app.models.knowledge import DocumentMetadata, DocumentStatus, VisibilityScope

import tiktoken


def _get_tokenizer() -> tiktoken.Encoding | None:
    """统一使用 tiktoken 的 cl100k_base 作为 token 计数器。

    若首次下载失败（如测试环境无网），返回 None，由 count_tokens fallback。
    """
    try:
        return tiktoken.get_encoding("cl100k_base")
    except Exception:
        return None


_tokenizer_instance: tiktoken.Encoding | None = None


def count_tokens(text: str) -> int:
    """计算文本的 token 数。

    首版统一 tiktoken；下载不可用时按中文字符 ~1.5 token/字估算，
    保证切分流程不因 tokenizer 初始化失败而中断。
    """
    global _tokenizer_instance
    if _tokenizer_instance is None:
        _tokenizer_instance = _get_tokenizer()
    if _tokenizer_instance is not None:
        return len(_tokenizer_instance.encode(text))
    # fallback：英文字符 0.3 token/字，中文字符 1.5 token/字
    en_count = sum(1 for c in text if c.isascii())
    cn_count = len(text) - en_count
    return int(en_count * 0.3 + cn_count * 1.5)


def compute_checksum(content: bytes) -> str:
    """计算文件内容 checksum，用于去重与变更检测。"""
    return hashlib.sha256(content).hexdigest()


# 默认 chunk 参数（设计文档硬性规定：512 tokens + 128 overlap）
DEFAULT_CHUNK_SIZE = 512
DEFAULT_CHUNK_OVERLAP = 128

# 允许特化策略的文档类型范围（设计文档硬性规定）
OVERRIDE_DOC_TYPES = {"合同", "协议", "表格", "流程表单", "审批模板", "通知", "公告"}


@dataclass
class ChunkingStrategy:
    """切分策略。"""

    chunk_size: int
    chunk_overlap: int


class ChunkingStrategyResolver:
    """根据文档类型解析切分策略。

    默认 512/128；仅在文档类型明确属于 OVERRIDE_DOC_TYPES 时才允许覆盖为 1024/256。
    """

    def resolve(self, doc_type: str, title: str = "") -> ChunkingStrategy:
        """返回对应文档类型的切分策略。"""
        normalized = (doc_type + title).lower()
        if any(keyword in normalized for keyword in OVERRIDE_DOC_TYPES):
            # 长条款/表格类文档允许更大上下文
            return ChunkingStrategy(chunk_size=1024, chunk_overlap=256)
        return ChunkingStrategy(chunk_size=DEFAULT_CHUNK_SIZE, chunk_overlap=DEFAULT_CHUNK_OVERLAP)


@dataclass
class IngestionResult:
    """接入结果。"""

    doc_id: str
    status: str  # active / parse_failed / index_failed / sync_pending
    chunk_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class KnowledgeIngestionService:
    """知识接入服务：上传 -> 解析 -> 切分 -> 索引。"""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._metadata_path = self._settings.knowledge_metadata_path
        self._metadata_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._metadata_path.exists():
            self._metadata_path.write_text("[]", encoding="utf-8")

    def ingest(
        self,
        filename: str,
        content: bytes,
        department: str,
        *,
        title: str = "",
        visibility_scope: VisibilityScope = VisibilityScope.DEPARTMENT,
        owner_user_id: str = "",
    ) -> IngestionResult:
        """执行完整接入流程（骨架）。"""
        raise NotImplementedError

    def retry_parse(self, doc_id: str) -> IngestionResult | None:
        """对 parse_failed 的文档重试解析。"""
        raise NotImplementedError

    def retry_index(self, doc_id: str) -> IngestionResult | None:
        """对 index_failed 的文档重试索引。"""
        raise NotImplementedError
