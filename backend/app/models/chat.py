"""聊天接口模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.domain import HistorySession


class ChatStreamRequest(BaseModel):
    """对话请求。"""

    session_id: str = Field(default="default-session")
    query: str


class ChatHistoryResponse(BaseModel):
    """历史记录响应。"""

    items: list[HistorySession]
    total: int


class DeleteSessionResponse(BaseModel):
    """删除会话响应。"""

    deleted: bool
    session_id: str


class RenameSessionRequest(BaseModel):
    """重命名会话请求。"""

    title: str = Field(min_length=1, max_length=60)


class RenameSessionResponse(BaseModel):
    """重命名会话响应。"""

    session_id: str
    title: str
