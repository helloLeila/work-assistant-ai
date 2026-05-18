"""知识库服务测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.models.knowledge import DocumentStatus, VisibilityScope
from app.services.knowledge_service import KnowledgeService


@pytest.fixture
def temp_knowledge_metadata(tmp_path, monkeypatch):
    """提供隔离的 metadata 文件。"""
    metadata_path = tmp_path / "knowledge_metadata.json"
    monkeypatch.setattr(
        get_settings(), "knowledge_metadata_path", metadata_path
    )
    return metadata_path


def test_migration_on_init(temp_knowledge_metadata: Path) -> None:
    """初始化时应自动迁移旧 metadata。"""
    old_data = [
        {
            "doc_id": "doc-old-1",
            "filename": "old.pdf",
            "department": "HR",
            "upload_time": "2024-01-01T00:00:00",
        }
    ]
    temp_knowledge_metadata.write_text(
        json.dumps(old_data, ensure_ascii=False), encoding="utf-8"
    )

    service = KnowledgeService()
    docs = service.list_documents()

    assert len(docs) == 1
    migrated = docs[0]
    assert migrated["doc_id"] == "doc-old-1"
    assert migrated.get("version") == "v1.0"
    assert migrated.get("visibility_scope") == VisibilityScope.DEPARTMENT.value
    assert migrated.get("status") == DocumentStatus.ACTIVE.value
    assert migrated.get("is_latest") is True
