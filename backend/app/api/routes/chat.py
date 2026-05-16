"""聊天路由。"""

from __future__ import annotations

import ipaddress

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.api.deps import get_current_user
from app.core.security import CurrentUser
from app.models.chat import (
    ChatHistoryResponse,
    ChatStreamRequest,
    DeleteSessionResponse,
    RenameSessionRequest,
    RenameSessionResponse,
)
from app.services.chat_service import get_chat_service
from app.services.history_service import get_history_service

router = APIRouter(prefix="/chat")


def _is_private_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
        return addr.is_private or addr.is_loopback or addr.is_link_local
    except ValueError:
        return True


def _extract_client_ip(request: Request) -> str | None:
    """提取真实公网 IP，兼容反向代理。"""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        for candidate in forwarded.split(","):
            ip = candidate.strip()
            if ip and not _is_private_ip(ip):
                return ip

    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        ip = real_ip.strip()
        if ip and not _is_private_ip(ip):
            return ip

    if request.client and request.client.host:
        host = request.client.host.strip()
        if host and not _is_private_ip(host):
            return host

    return None


@router.post("/stream")
async def chat_stream(
    payload: ChatStreamRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    """通过 POST 发起 SSE 对话流。"""
    generator = get_chat_service().create_stream_generator(
        session_id=payload.session_id,
        query=payload.query,
        current_user=current_user,
        client_ip=_extract_client_ip(request),
    )
    return StreamingResponse(generator, media_type="text/event-stream")


@router.get("/stream")
async def chat_stream_get(
    request: Request,
    session_id: str = Query(...),
    query: str = Query(...),
    current_user: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    """为浏览器 EventSource 提供 GET 版 SSE。"""
    generator = get_chat_service().create_stream_generator(
        session_id=session_id,
        query=query,
        current_user=current_user,
        client_ip=_extract_client_ip(request),
    )
    return StreamingResponse(generator, media_type="text/event-stream")


@router.get("/history", response_model=ChatHistoryResponse)
async def list_history(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
) -> ChatHistoryResponse:
    """查询历史记录。"""
    items, total = get_history_service().list_sessions(current_user.user_id, page=page, page_size=page_size)
    return ChatHistoryResponse(items=items, total=total)


@router.delete("/session/{session_id}", response_model=DeleteSessionResponse)
async def delete_session(
    session_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> DeleteSessionResponse:
    """删除某个会话。"""
    deleted = get_history_service().delete_session(current_user.user_id, session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="会话不存在")
    return DeleteSessionResponse(deleted=True, session_id=session_id)


@router.patch("/session/{session_id}", response_model=RenameSessionResponse)
async def rename_session(
    session_id: str,
    payload: RenameSessionRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> RenameSessionResponse:
    """重命名会话。"""
    success = get_history_service().rename_session(
        current_user.user_id, session_id, payload.title
    )
    if not success:
        raise HTTPException(status_code=404, detail="会话不存在")
    return RenameSessionResponse(session_id=session_id, title=payload.title.strip()[:60])
