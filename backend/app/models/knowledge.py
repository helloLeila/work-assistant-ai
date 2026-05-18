"""知识库模型。"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class DocumentStatus(str, Enum):
    """文档状态。"""

    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"
    SYNC_PENDING = "sync_pending"
    MIGRATION_PENDING = "migration_pending"
    PARSE_FAILED = "parse_failed"
    INDEX_FAILED = "index_failed"


class VisibilityScope(str, Enum):
    """可见范围。"""

    PUBLIC = "public"
    DEPARTMENT = "department"
    PRIVATE = "private"
    PROJECT = "project"


class DocumentMetadata(BaseModel):
    """文档级元数据。"""

    doc_id: str
    title: str = ""
    source_file: str = ""
    department: str = ""
    visibility_scope: VisibilityScope = VisibilityScope.DEPARTMENT
    owner_user_id: str = ""
    project_ids: list[str] = Field(default_factory=list)
    status: DocumentStatus = DocumentStatus.ACTIVE
    version: str = "v1.0"
    is_latest: bool = True
    effective_at: str = ""
    expires_at: str = ""
    maintainer: str = ""
    upload_time: str = ""
    checksum: str = ""
    chunk_count: int = 0
    storage_path: str = ""


class ChunkMetadata(BaseModel):
    """Chunk 级元数据。"""

    chunk_id: str
    doc_id: str
    chunk_index: int
    section_path: str = ""
    token_count: int = 0
    status: DocumentStatus = DocumentStatus.ACTIVE
    version: str = "v1.0"
    is_latest: bool = True
    visibility_scope: VisibilityScope = VisibilityScope.DEPARTMENT
    department: str = ""
    source_file: str = ""
    page_num: int = 1


class KnowledgeDocumentItem(BaseModel):
    """知识库文档元信息。"""

    doc_id: str
    filename: str
    department: str
    doc_type: str
    upload_time: str
    chunk_count: int


class KnowledgeListResponse(BaseModel):
    """知识库列表响应。"""

    items: list[KnowledgeDocumentItem]


class KnowledgeUploadResponse(BaseModel):
    """上传响应。"""

    doc_id: str
    filename: str
    chunk_count: int
    department: str
    indexed: bool


class DeleteKnowledgeResponse(BaseModel):
    """删除响应。"""

    deleted: bool
    doc_id: str
