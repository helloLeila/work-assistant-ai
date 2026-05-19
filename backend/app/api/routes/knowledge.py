"""知识库路由。

本模块提供知识库的文档管理与检索接口。上传/列出/删除由 KnowledgeService 处理；
检索查询由 run_retrieval_pipeline 处理，返回结构化的 KnowledgeAnswerPayload，
包含回答文本、引用来源与检索调试追踪。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.api.deps import get_current_user
from app.chains.rag_chain import run_retrieval_pipeline
from app.core.security import CurrentUser
from app.models.knowledge import DeleteKnowledgeResponse, KnowledgeListResponse, KnowledgeUploadResponse
from app.models.knowledge_retrieval import KnowledgeAnswerPayload
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


@router.post("/search", response_model=KnowledgeAnswerPayload)
async def search_knowledge(
    query: str = Form(...),
    current_user: CurrentUser = Depends(get_current_user),
) -> KnowledgeAnswerPayload:
    """执行知识库检索，返回结构化检索结果。

    本路由直接调用 run_retrieval_pipeline 执行完整的企业 RAG 检索链路，
    返回包含 answer、citations（引用来源）与 retrieval_debug（调试追踪）的
    KnowledgeAnswerPayload，供前端直接展示或进一步处理。

    参数：
    - query: 用户查询字符串（Form 格式）；
    - current_user: 当前登录用户，用于 ACL 权限解析。

    返回值：
    KnowledgeAnswerPayload，包含回答文本、引用列表与检索调试信息。
    """
    return await run_retrieval_pipeline(query, user=current_user)


@router.delete("/{doc_id}", response_model=DeleteKnowledgeResponse)
async def delete_document(doc_id: str, current_user: CurrentUser = Depends(get_current_user)) -> DeleteKnowledgeResponse:
    """删除知识文档。"""
    if current_user.role not in {"hr_admin", "knowledge_admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前账号没有删除文档的权限")
    deleted = get_knowledge_service().delete_document(doc_id)
    return DeleteKnowledgeResponse(deleted=deleted, doc_id=doc_id)
