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
