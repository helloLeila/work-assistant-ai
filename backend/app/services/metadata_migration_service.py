"""知识库元数据迁移规则。

旧数据迁移默认规则：
- 新文档默认 version=v1.0
- 未显式传 effective_at 时，默认"上传即生效"
- 若未设置 expires_at，表示长期有效
- 旧数据迁移时，若已有 department，默认 visibility_scope=department
- 仅在历史数据连 department 都缺失时，才允许降级成 public
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models.knowledge import DocumentMetadata, DocumentStatus, VisibilityScope


def migrate_document_metadata(raw: dict[str, Any]) -> DocumentMetadata:
    """把旧 metadata 字典迁移为新的 DocumentMetadata。"""
    doc_id = str(raw.get("doc_id", ""))
    department = str(raw.get("department", ""))

    # 旧数据迁移：有 department 默认 visibility_scope=department，否则 public
    scope = str(raw.get("visibility_scope", ""))
    if not scope:
        scope = VisibilityScope.DEPARTMENT.value if department else VisibilityScope.PUBLIC.value

    # version 默认 v1.0
    version = str(raw.get("version", "")) or "v1.0"

    # effective_at 默认上传时间或当前时间
    effective_at = str(raw.get("effective_at", ""))
    upload_time = str(raw.get("upload_time", ""))
    if not effective_at:
        effective_at = upload_time or datetime.now(timezone.utc).isoformat()

    # expires_at 为空表示长期有效
    expires_at = str(raw.get("expires_at", ""))

    # status 默认 active；旧数据无状态字段时补 active
    status_str = str(raw.get("status", "")) or DocumentStatus.ACTIVE.value

    # checksum 缺失时为空
    checksum = str(raw.get("checksum", ""))

    return DocumentMetadata(
        doc_id=doc_id,
        title=str(raw.get("title", "")),
        source_file=str(raw.get("source_file", raw.get("filename", ""))),
        department=department,
        visibility_scope=VisibilityScope(scope),
        owner_user_id=str(raw.get("owner_user_id", "")),
        project_ids=list(raw.get("project_ids", [])),
        status=DocumentStatus(status_str),
        version=version,
        is_latest=bool(raw.get("is_latest", True)),
        effective_at=effective_at,
        expires_at=expires_at,
        maintainer=str(raw.get("maintainer", "")),
        upload_time=upload_time,
        checksum=checksum,
        doc_type=str(raw.get("doc_type", "")),
        chunk_count=int(raw.get("chunk_count", 0)),
        storage_path=str(raw.get("storage_path", "")),
    )


def needs_migration(raw: dict[str, Any]) -> bool:
    """判断旧 metadata 是否需要迁移。"""
    required_keys = {
        "version",
        "visibility_scope",
        "status",
        "is_latest",
        "effective_at",
    }
    return not required_keys.issubset(set(raw.keys()))
