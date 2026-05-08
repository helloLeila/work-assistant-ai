"""聊天历史服务。"""

from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache

from app.core.config import get_settings
from app.models.domain import ChatTurn, HistorySession, SourceCitation


class HistoryService:
    """维护聊天历史。"""

    def __init__(self) -> None:
        self._path = get_settings().chat_history_path
        if not self._path.exists():
            self._path.write_text("{}", encoding="utf-8")

    def list_sessions(self, user_id: str, page: int = 1, page_size: int = 20) -> tuple[list[HistorySession], int]:
        """分页返回会话。"""
        sessions = list(self._load_all().get(user_id, {}).values())
        sessions.sort(key=lambda item: item["updated_at"], reverse=True)
        total = len(sessions)
        start = max(page - 1, 0) * page_size
        end = start + page_size
        return [HistorySession.model_validate(item) for item in sessions[start:end]], total

    def append_turn(
        self,
        *,
        user_id: str,
        session_id: str,
        title: str,
        role: str,
        content: str,
        sources: list[dict[str, object]] | None = None,
    ) -> None:
        """追加消息。"""
        payload = self._load_all()
        user_sessions = payload.setdefault(user_id, {})
        is_new_session = session_id not in user_sessions
        session = user_sessions.setdefault(
            session_id,
            {
                "session_id": session_id,
                "title": title,
                "updated_at": datetime.utcnow().isoformat(),
                "turns": [],
            },
        )
        # 只有在“会话第一次创建”时才用 query 自动生成标题。
        # 之后无论用户改没改名，都不再覆盖，避免重命名被下一条消息冲掉。
        if is_new_session:
            session["title"] = title
        session["updated_at"] = datetime.utcnow().isoformat()
        session["turns"].append(
            ChatTurn(
                role=role,
                content=content,
                created_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                sources=[SourceCitation.model_validate(item) for item in (sources or [])],
            ).model_dump()
        )
        self._save_all(payload)

    def rename_session(self, user_id: str, session_id: str, title: str) -> bool:
        """重命名会话，返回是否成功（False 表示会话不存在）。"""
        payload = self._load_all()
        user_sessions = payload.get(user_id, {})
        session = user_sessions.get(session_id)
        if session is None:
            return False
        session["title"] = title.strip()[:60]
        session["updated_at"] = datetime.utcnow().isoformat()
        self._save_all(payload)
        return True

    def delete_session(self, user_id: str, session_id: str) -> bool:
        """删除会话。"""
        payload = self._load_all()
        user_sessions = payload.setdefault(user_id, {})
        deleted = user_sessions.pop(session_id, None) is not None
        self._save_all(payload)
        return deleted

    def _load_all(self) -> dict[str, dict[str, dict[str, object]]]:
        return json.loads(self._path.read_text(encoding="utf-8"))

    def _save_all(self, payload: dict[str, object]) -> None:
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


@lru_cache
def get_history_service() -> HistoryService:
    return HistoryService()
