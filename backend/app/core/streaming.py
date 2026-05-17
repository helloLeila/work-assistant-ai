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

    async def push_status(self, *, step: str, label: str, state: str) -> None:
        """推送管道级状态事件。

        用于让前端在"模型还没吐 token"的几秒里，知道后端在干什么——
        例如 RAG 场景下 intent_router / knowledge_rag / grader 都是非流式 LLM 调用，
        以前这段时间前端只能看到死秒表，现在可以显示"检索知识库中…""筛选相关内容…"。

        参数设计：
        - step：稳定的机器 id（intent / retrieve / grade / generate …），前端用它 upsert 同一条。
        - label：给用户看的中文描述，可以随节点变化而微调。
        - state：running / done，前端据此切换 spinner/对勾图标。
        """
        await self._queue.put(
            StreamEvent(
                type="status",
                payload={"step": step, "label": label, "state": state},
            )
        )

    async def push_progress(self, *, step: str, detail: str) -> None:
        """推送某个长步骤内部的细粒度进展。"""
        await self._queue.put(
            StreamEvent(
                type="progress",
                payload={"step": step, "detail": detail},
            )
        )

    async def push_trace(
        self,
        *,
        step: str,
        label: str,
        detail: str = "",
        state: str = "done",
    ) -> None:
        """推送可回放的处理轨迹，用于前端展开查看。"""
        await self._queue.put(
            StreamEvent(
                type="trace",
                payload={"step": step, "label": label, "detail": detail, "state": state},
            )
        )

    async def push_sources(self, files: list[dict[str, Any]]) -> None:
        await self._queue.put(StreamEvent(type="source", payload={"files": files}))

    async def push_artifact(self, artifact: dict[str, Any]) -> None:
        """推送结构化 artifact，供前端渲染天气/日期卡片。"""
        await self._queue.put(StreamEvent(type="artifact", payload={"artifact": artifact}))

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
