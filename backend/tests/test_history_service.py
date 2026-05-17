"""历史服务的 artifact 回归测试。"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from app.services.history_service import HistoryService


def test_append_turn_persists_artifacts(tmp_path, monkeypatch) -> None:
    """聊天轮次写入时应把 artifacts 一并落盘。"""
    history_path = tmp_path / "chat_history.json"
    monkeypatch.setattr(
        "app.services.history_service.get_settings",
        lambda: SimpleNamespace(chat_history_path=history_path),
    )

    service = HistoryService()
    service.append_turn(
        user_id="user-1",
        session_id="session-1",
        title="天气",
        role="assistant",
        content="深圳今天多云。",
        sources=[],
        artifacts=[{"kind": "weather_card", "version": 1, "data": {"city": "深圳"}}],
    )

    payload = json.loads(Path(history_path).read_text(encoding="utf-8"))
    turn = payload["user-1"]["session-1"]["turns"][0]
    assert turn["artifacts"][0]["kind"] == "weather_card"


def test_list_sessions_handles_legacy_turn_without_artifacts(tmp_path, monkeypatch) -> None:
    """旧历史没有 artifacts 字段时也应能正常读出来。"""
    history_path = tmp_path / "chat_history.json"
    history_path.write_text(
        json.dumps(
            {
                "user-1": {
                    "session-1": {
                        "session_id": "session-1",
                        "title": "旧会话",
                        "updated_at": "2026-05-17T10:00:00",
                        "turns": [
                            {
                                "role": "assistant",
                                "content": "hello",
                                "created_at": "2026-05-17 10:00:00",
                                "sources": [],
                            }
                        ],
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.services.history_service.get_settings",
        lambda: SimpleNamespace(chat_history_path=history_path),
    )

    service = HistoryService()
    sessions, total = service.list_sessions("user-1")

    assert total == 1
    assert sessions[0].turns[0].artifacts == []
