"""知识库路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.api.deps import get_current_user
from app.core.security import CurrentUser
from app.models.knowledge import DeleteKnowledgeResponse, KnowledgeListResponse, KnowledgeUploadResponse
from app.services.knowledge_service import get_knowledge_service

router = APIRouter(prefix="/knowledge")


@router.post("/upload", response_model=KnowledgeUploadResponse)
async def upload_document(
    department: str = Form(...),
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
) -> KnowledgeUploadResponse:
    """上传知识文档。"""
    if current_user.role not in {"hr_admin", "knowledge_admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前账号没有上传文档的权限")
    content = await file.read()
    result = get_knowledge_service().upload_document(file.filename, content, department)
    return KnowledgeUploadResponse(**result)


@router.get("/list", response_model=KnowledgeListResponse)
async def list_documents(current_user: CurrentUser = Depends(get_current_user)) -> KnowledgeListResponse:
    """列出知识库文档。"""
    _ = current_user
    items = get_knowledge_service().list_documents()
    return KnowledgeListResponse(items=items)


@router.delete("/{doc_id}", response_model=DeleteKnowledgeResponse)
async def delete_document(doc_id: str, current_user: CurrentUser = Depends(get_current_user)) -> DeleteKnowledgeResponse:
    """删除知识文档。"""
    if current_user.role not in {"hr_admin", "knowledge_admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前账号没有删除文档的权限")
    deleted = get_knowledge_service().delete_document(doc_id)
    return DeleteKnowledgeResponse(deleted=deleted, doc_id=doc_id)
