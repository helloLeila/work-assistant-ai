"""API 依赖项。"""

from __future__ import annotations

from fastapi import Header, HTTPException, Query, status

from app.core.security import CurrentUser, decode_access_token


def _resolve_token(authorization: str | None = None, access_token: str | None = None) -> str:
    if authorization and authorization.startswith("Bearer "):
        return authorization.replace("Bearer ", "", 1).strip()
    if access_token:
        return access_token
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少访问令牌")


def get_current_user(
    authorization: str | None = Header(default=None),
    access_token: str | None = Query(default=None),
) -> CurrentUser:
    """获取当前用户。"""
    token = _resolve_token(authorization=authorization, access_token=access_token)
    try:
        return decode_access_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
