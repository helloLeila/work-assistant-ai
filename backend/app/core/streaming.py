"""SSE 事件流辅助。"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any


@dataclass
class StreamEvent:
    """SSE 单个事件。"""

    type: str
    payload: dict[str, Any]


class SSEStreamer:
    """用于后台任务与 HTTP 响应之间传递事件。"""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[StreamEvent | None] = asyncio.Queue()

    async def push_token(self, token: str) -> None:
        await self._queue.put(StreamEvent(type="token", payload={"content": token}))

    async def push_thinking(self, chunk: str) -> None:
        """推送一段思考过程文本（与 token 同级，但前端单独渲染折叠块）。"""
        await self._queue.put(StreamEvent(type="thinking", payload={"content": chunk}))

    async def push_sources(self, files: list[dict[str, Any]]) -> None:
        await self._queue.put(StreamEvent(type="source", payload={"files": files}))

    async def push_error(self, message: str) -> None:
        await self._queue.put(StreamEvent(type="error", payload={"message": message}))

    async def push_done(self) -> None:
        await self._queue.put(StreamEvent(type="done", payload={}))
        await self._queue.put(None)

    async def iter_sse(self):
        """以 SSE 格式输出事件。"""
        while True:
            event = await self._queue.get()
            if event is None:
                break
            body = {"type": event.type, **event.payload}
            yield f"data: {json.dumps(body, ensure_ascii=False, separators=(',', ':'))}\n\n"
