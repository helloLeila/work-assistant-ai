"""元数据迁移服务测试。"""

from __future__ import annotations

from app.models.knowledge import DocumentStatus, VisibilityScope
from app.services.metadata_migration_service import migrate_document_metadata, needs_migration


def test_migrate_old_metadata_with_department() -> None:
    raw = {
        "doc_id": "doc-001",
        "filename": "制度.pdf",
        "department": "HR",
        "upload_time": "2024-01-01T00:00:00",
    }
    doc = migrate_document_metadata(raw)
    assert doc.doc_id == "doc-001"
    assert doc.department == "HR"
    assert doc.visibility_scope == VisibilityScope.DEPARTMENT
    assert doc.version == "v1.0"
    assert doc.status == DocumentStatus.ACTIVE
    assert doc.is_latest is True
    assert doc.effective_at == "2024-01-01T00:00:00"
    assert doc.expires_at == ""
    assert doc.source_file == "制度.pdf"


def test_migrate_old_metadata_without_department() -> None:
    raw = {
        "doc_id": "doc-002",
        "filename": "公告.pdf",
        "upload_time": "2024-02-01T00:00:00",
    }
    doc = migrate_document_metadata(raw)
    assert doc.department == ""
    assert doc.visibility_scope == VisibilityScope.PUBLIC


def test_migrate_preserves_existing_fields() -> None:
    raw = {
        "doc_id": "doc-003",
        "version": "v2.1",
        "visibility_scope": "private",
        "status": "deprecated",
        "is_latest": False,
        "effective_at": "2024-06-01T00:00:00",
        "expires_at": "2025-06-01T00:00:00",
        "department": "Finance",
    }
    doc = migrate_document_metadata(raw)
    assert doc.version == "v2.1"
    assert doc.visibility_scope == VisibilityScope.PRIVATE
    assert doc.status == DocumentStatus.DEPRECATED
    assert doc.is_latest is False
    assert doc.effective_at == "2024-06-01T00:00:00"
    assert doc.expires_at == "2025-06-01T00:00:00"


def test_needs_migration_true() -> None:
    assert needs_migration({"doc_id": "x"}) is True
    assert needs_migration({"doc_id": "x", "version": "v1.0"}) is True


def test_needs_migration_false() -> None:
    assert needs_migration({"doc_id": "x", "version": "v1.0", "visibility_scope": "public", "status": "active", "is_latest": True, "effective_at": "2024-01-01"}) is False
