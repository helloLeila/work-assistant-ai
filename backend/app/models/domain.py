"""业务域模型。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SourceCitation(BaseModel):
    """知识引用。"""

    doc_id: str
    source_file: str
    page_num: int
    department: str
    score: float
    snippet: str


class IntentClassification(BaseModel):
    """意图分类结果。"""

    intent: str = Field(description="knowledge/salary/personal/travel/chitchat/clarify/web_research_write/direct_write")
    confidence: float = Field(description="0 到 1 之间的置信度")
    candidate_intents: list[str] = Field(default_factory=list)
    reason: str = ""


class GradeResult(BaseModel):
    """检索结果评估。"""

    relevant: bool
    score: float
    reason: str


class PersonalQuery(BaseModel):
    """个人信息查询结构。"""

    target_user_id: str | None = None
    requested_fields: list[str] = Field(default_factory=list)


class TravelInfo(BaseModel):
    """商旅结构化信息。"""

    from_city: str
    to_city: str
    date: str
    passengers: int = 1
    cabin_class: str = "经济舱"


class TravelOrder(BaseModel):
    """商旅订单信息。"""

    order_id: str
    status: str
    itinerary_summary: str
    provider: str = "local"
    booking_reference: str | None = None


class PermissionDecision(BaseModel):
    """权限判断结果。"""

    allowed: bool
    message: str = ""
    target_user_id: str | None = None


class ChatTurn(BaseModel):
    """聊天轮次。"""

    role: str
    content: str
    created_at: str
    sources: list[SourceCitation] = Field(default_factory=list)


class HistorySession(BaseModel):
    """历史会话。"""

    session_id: str
    title: str
    updated_at: str
    turns: list[ChatTurn] = Field(default_factory=list)


class GraphBlueprint(BaseModel):
    """图蓝图。"""

    entrypoint: str
    nodes: list[str]
    edges: dict[str, list[str]]
    features: list[str]
    checkpoint: str


class WebSearchHit(BaseModel):
    """Bocha 单条搜索结果。"""

    title: str
    url: str
    snippet: str
    site_name: str = ""
    published_at: str = ""


class WebSearchResult(BaseModel):
    """Bocha 搜索返回结构。"""

    query: str
    results: list[WebSearchHit]
    elapsed_ms: int = 0


class ToolResult(BaseModel):
    """工具调用结果。"""

    data: dict[str, Any]
