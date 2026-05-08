"""知识库模型。"""

from __future__ import annotations

from pydantic import BaseModel


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
