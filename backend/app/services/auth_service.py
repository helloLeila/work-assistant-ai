"""认证服务。"""

from __future__ import annotations

from functools import lru_cache

from app.core.security import (
    CurrentUser,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from app.models.auth import TokenResponse, UserProfile
from app.services.seed_data import EMPLOYEES


class AuthService:
    """处理登录与刷新。"""

    def __init__(self) -> None:
        self._users = []
        for item in EMPLOYEES:
            copied = dict(item)
            copied["password_hash"] = hash_password(str(copied.pop("password")))
            self._users.append(copied)

    def authenticate(self, username: str, password: str) -> TokenResponse | None:
        """校验账号密码。"""
        user = next((item for item in self._users if item["username"] == username), None)
        if not user or not verify_password(password, str(user["password_hash"])):
            return None
        return self._build_token_response(user)

    def refresh(self, refresh_token: str) -> TokenResponse:
        """刷新访问令牌。"""
        current_user = decode_refresh_token(refresh_token)
        user = self.get_user_by_id(current_user.user_id)
        return self._build_token_response(user)

    def get_user_by_id(self, user_id: str) -> dict[str, object]:
        """按 ID 查询用户。"""
        user = next((item for item in self._users if item["user_id"] == user_id), None)
        if user is None:
            raise ValueError("用户不存在")
        return user

    def get_current_user_profile(self, user: CurrentUser) -> UserProfile:
        """把当前用户转成公开资料。"""
        return UserProfile(
            user_id=user.user_id,
            username=user.username,
            name=user.name,
            role=user.role,
            department=user.department,
            manager_id=user.manager_id,
        )

    def _build_token_response(self, user: dict[str, object]) -> TokenResponse:
        payload = {
            "sub": str(user["user_id"]),
            "username": str(user["username"]),
            "name": str(user["name"]),
            "role": str(user["role"]),
            "department": str(user["department"]),
            "manager_id": str(user["manager_id"]) if user["manager_id"] is not None else None,
        }
        access_token = create_access_token(payload)
        refresh_token = create_refresh_token(payload)
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=UserProfile(
                user_id=str(user["user_id"]),
                username=str(user["username"]),
                name=str(user["name"]),
                role=str(user["role"]),
                department=str(user["department"]),
                manager_id=str(user["manager_id"]) if user["manager_id"] is not None else None,
            ),
        )


@lru_cache
def get_auth_service() -> AuthService:
    """获取认证服务单例。"""
    return AuthService()
