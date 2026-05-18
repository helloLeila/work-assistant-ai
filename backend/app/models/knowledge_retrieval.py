"""检索载荷与日志模型。"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RetrievalProfile(str, Enum):
    """检索档位。"""

    FAQ_LOW_COST = "faq_low_cost"
    STANDARD = "standard"
    HIGH_RECALL = "high_recall"


class BiasMode(str, Enum):
    """检索偏向总开关。"""

    BALANCED = "balanced"
    SEMANTIC_BIAS = "semantic_bias"
    KEYWORD_BIAS = "keyword_bias"


class AccessPolicy(BaseModel):
    """ACL 统一输出。"""

    allowed_departments: list[str] = Field(default_factory=list)
    allowed_project_ids: list[str] = Field(default_factory=list)
    can_read_private_doc_ids: list[str] = Field(default_factory=list)
    milvus_filter: str = ""


class QueryRewriteResult(BaseModel):
    """查询改写结果。"""

    original_query: str = ""
    rewritten_query: str = ""
    keywords: list[str] = Field(default_factory=list)
    strategy: str = "light_rewrite"
    retry_count: int = 0


class CitationItem(BaseModel):
    """单条引用。"""

    doc_id: str
    chunk_id: str = ""
    source_file: str = ""
    section_path: str = ""
    version: str = ""
    snippet: str = ""


class RetrievalDebugTrace(BaseModel):
    """检索调试追踪。"""

    original_query: str = ""
    rewritten_query: str = ""
    acl_filter: str = ""
    profile: RetrievalProfile = RetrievalProfile.STANDARD
    bias_mode: BiasMode = BiasMode.BALANCED
    dense_candidates: list[dict[str, Any]] = Field(default_factory=list)
    sparse_candidates: list[dict[str, Any]] = Field(default_factory=list)
    rrf_merged: list[dict[str, Any]] = Field(default_factory=list)
    reranked_top: list[dict[str, Any]] = Field(default_factory=list)
    low_confidence: bool = False
    low_recall: bool = False
    rewrite_retry_count: int = 0
    fallback_triggered: str = ""


class AccessAuditLog(BaseModel):
    """访问审计日志。"""

    user_id: str = ""
    user_roles: list[str] = Field(default_factory=list)
    client_ip: str = ""
    query: str = ""
    matched_doc_ids: list[str] = Field(default_factory=list)
    blocked_doc_ids: list[str] = Field(default_factory=list)
    deny_reason: str = ""
    request_start: str = ""
    request_end: str = ""
    timestamp: str = ""


class KnowledgeAnswerPayload(BaseModel):
    """知识回答载荷。"""

    answer: str = ""
    citations: list[CitationItem] = Field(default_factory=list)
    retrieval_debug: RetrievalDebugTrace = Field(default_factory=RetrievalDebugTrace)
