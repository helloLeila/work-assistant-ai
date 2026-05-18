"""知识库模型测试。"""

from __future__ import annotations

from app.models.knowledge import (
    ChunkMetadata,
    DocumentMetadata,
    DocumentStatus,
    VisibilityScope,
)


def test_document_status_enum() -> None:
    assert DocumentStatus.ACTIVE.value == "active"
    assert DocumentStatus.DEPRECATED.value == "deprecated"
    assert DocumentStatus.DRAFT.value == "draft"
    assert DocumentStatus.ARCHIVED.value == "archived"
    assert DocumentStatus.SYNC_PENDING.value == "sync_pending"
    assert DocumentStatus.MIGRATION_PENDING.value == "migration_pending"
    assert DocumentStatus.PARSE_FAILED.value == "parse_failed"
    assert DocumentStatus.INDEX_FAILED.value == "index_failed"


def test_visibility_scope_enum() -> None:
    assert VisibilityScope.PUBLIC.value == "public"
    assert VisibilityScope.DEPARTMENT.value == "department"
    assert VisibilityScope.PRIVATE.value == "private"
    assert VisibilityScope.PROJECT.value == "project"


def test_document_metadata_defaults() -> None:
    doc = DocumentMetadata(doc_id="doc-123")
    assert doc.doc_id == "doc-123"
    assert doc.version == "v1.0"
    assert doc.is_latest is True
    assert doc.visibility_scope == VisibilityScope.DEPARTMENT
    assert doc.status == DocumentStatus.ACTIVE
    assert doc.title == ""
    assert doc.owner_user_id == ""
    assert doc.project_ids == []


def test_chunk_metadata_defaults() -> None:
    chunk = ChunkMetadata(chunk_id="chunk-1", doc_id="doc-123", chunk_index=0)
    assert chunk.chunk_id == "chunk-1"
    assert chunk.doc_id == "doc-123"
    assert chunk.chunk_index == 0
    assert chunk.version == "v1.0"
    assert chunk.is_latest is True
    assert chunk.visibility_scope == VisibilityScope.DEPARTMENT
    assert chunk.status == DocumentStatus.ACTIVE
    assert chunk.section_path == ""
    assert chunk.token_count == 0
