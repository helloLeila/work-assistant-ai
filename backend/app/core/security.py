"""认证与安全模块。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from passlib.hash import pbkdf2_sha256
from pydantic import BaseModel, Field

from app.core.config import get_settings


class TokenPayload(BaseModel):
    """令牌载荷。"""

    sub: str
    username: str
    name: str
    role: str
    department: str
    manager_id: str | None = None
    token_type: str = "access"
    exp: int


class CurrentUser(BaseModel):
    """当前用户上下文。"""

    user_id: str = Field(alias="sub")
    username: str
    name: str
    role: str
    department: str
    manager_id: str | None = None

    model_config = {"populate_by_name": True}


def hash_password(password: str) -> str:
    """生成密码哈希。"""
    return pbkdf2_sha256.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """校验密码。"""
    return pbkdf2_sha256.verify(password, password_hash)


def create_access_token(data: dict[str, Any]) -> str:
    """签发访问令牌。"""
    settings = get_settings()
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {**data, "token_type": "access", "exp": int(expires_at.timestamp())}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(data: dict[str, Any]) -> str:
    """签发刷新令牌。"""
    settings = get_settings()
    expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
    payload = {**data, "token_type": "refresh", "exp": int(expires_at.timestamp())}
    return jwt.encode(payload, settings.jwt_refresh_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> CurrentUser:
    """解析访问令牌。"""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        token_payload = TokenPayload.model_validate(payload)
    except JWTError as exc:
        raise ValueError("访问令牌无效") from exc

    if token_payload.token_type != "access":
        raise ValueError("访问令牌类型错误")
    return CurrentUser.model_validate(token_payload.model_dump())


def decode_refresh_token(token: str) -> CurrentUser:
    """解析刷新令牌。"""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_refresh_secret_key, algorithms=[settings.jwt_algorithm])
        token_payload = TokenPayload.model_validate(payload)
    except JWTError as exc:
        raise ValueError("刷新令牌无效") from exc

    if token_payload.token_type != "refresh":
        raise ValueError("刷新令牌类型错误")
    return CurrentUser.model_validate(token_payload.model_dump())
