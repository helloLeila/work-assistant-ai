"""认证模型。"""

from __future__ import annotations

from pydantic import BaseModel


class LoginRequest(BaseModel):
    """登录请求。"""

    username: str
    password: str


class RefreshTokenRequest(BaseModel):
    """刷新令牌请求。"""

    refresh_token: str


class UserProfile(BaseModel):
    """用户信息。"""

    user_id: str
    username: str
    name: str
    role: str
    department: str
    manager_id: str | None = None


class TokenResponse(BaseModel):
    """登录/刷新响应。"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserProfile
