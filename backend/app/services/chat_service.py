"""聊天编排服务。"""

from __future__ import annotations

import asyncio
from functools import lru_cache

from app.agents.office_assistant_graph import GraphRuntimeContext, get_office_assistant_graph
from app.core.security import CurrentUser
from app.core.streaming import SSEStreamer
from app.services.followup_service import answer_contextual_followup
from app.services.history_service import get_history_service


class ChatService:
    """协调图执行与历史记录。"""

    def __init__(self) -> None:
        self._graph = get_office_assistant_graph()
        self._history = get_history_service()

    async def run_streaming_chat(
        self,
        *,
        session_id: str,
        query: str,
        current_user: CurrentUser,
        streamer: SSEStreamer,
        client_ip: str | None = None,
    ) -> None:
        """执行图并推送流式事件。"""
        title = query[:24]
        self._history.append_turn(
            user_id=current_user.user_id,
            session_id=session_id,
            title=title,
            role="user",
            content=query,
        )

        try:
            followup_answer = answer_contextual_followup(
                query,
                self._history.get_last_assistant_content(current_user.user_id, session_id),
            )
            if followup_answer is not None:
                await streamer.push_status(step="followup", label="理解追问", state="running")
                await streamer.push_progress(step="followup", detail="结合上一轮薪酬结果解释权限脱敏")
                await streamer.push_status(step="followup", label="理解追问", state="done")
                for character in followup_answer:
                    await streamer.push_token(character)
                self._history.append_turn(
                    user_id=current_user.user_id,
                    session_id=session_id,
                    title=title,
                    role="assistant",
                    content=followup_answer,
                    sources=[],
                )
                await streamer.push_done()
                return

            state = await self._graph.ainvoke(
                {
                    "session_id": session_id,
                    "query": query,
                    "current_user": current_user,
                    "client_ip": client_ip,
                    "retry_count": 0,
                },
                {"configurable": {"thread_id": session_id}},
                context=GraphRuntimeContext(current_user=current_user, streamer=streamer),
            )
            sources = state.get("sources", [])
            if sources:
                await streamer.push_sources(sources)

            self._history.append_turn(
                user_id=current_user.user_id,
                session_id=session_id,
                title=title,
                role="assistant",
                content=state.get("final_answer", ""),
                sources=sources,
            )
            await streamer.push_done()
        except Exception as exc:
            await streamer.push_error(str(exc))
            await streamer.push_done()

    async def create_stream_generator(
        self,
        *,
        session_id: str,
        query: str,
        current_user: CurrentUser,
        client_ip: str | None = None,
    ):
        """创建 SSE 生成器。"""
        streamer = SSEStreamer()
        task = asyncio.create_task(
            self.run_streaming_chat(
                session_id=session_id,
                query=query,
                current_user=current_user,
                streamer=streamer,
                client_ip=client_ip,
            )
        )
        try:
            async for item in streamer.iter_sse():
                yield item
        finally:
            await task


@lru_cache
def get_chat_service() -> ChatService:
    return ChatService()
