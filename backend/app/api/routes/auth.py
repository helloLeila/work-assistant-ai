"""认证路由。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.models.auth import LoginRequest, RefreshTokenRequest, TokenResponse
from app.services.auth_service import get_auth_service

router = APIRouter(prefix="/auth")


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest) -> TokenResponse:
    """账号登录。"""
    result = get_auth_service().authenticate(payload.username, payload.password)
    if result is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    return result


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(payload: RefreshTokenRequest) -> TokenResponse:
    """刷新访问令牌。"""
    try:
        return get_auth_service().refresh(payload.refresh_token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
