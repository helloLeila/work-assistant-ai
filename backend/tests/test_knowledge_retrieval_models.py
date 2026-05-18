"""检索载荷模型测试。"""

from __future__ import annotations

from app.models.knowledge_retrieval import (
    AccessAuditLog,
    AccessPolicy,
    BiasMode,
    CitationItem,
    KnowledgeAnswerPayload,
    QueryRewriteResult,
    RetrievalDebugTrace,
    RetrievalProfile,
)


def test_retrieval_profile_enum() -> None:
    assert RetrievalProfile.STANDARD.value == "standard"
    assert RetrievalProfile.FAQ_LOW_COST.value == "faq_low_cost"
    assert RetrievalProfile.HIGH_RECALL.value == "high_recall"


def test_bias_mode_enum() -> None:
    assert BiasMode.BALANCED.value == "balanced"
    assert BiasMode.SEMANTIC_BIAS.value == "semantic_bias"
    assert BiasMode.KEYWORD_BIAS.value == "keyword_bias"


def test_access_policy_defaults() -> None:
    policy = AccessPolicy()
    assert policy.allowed_departments == []
    assert policy.allowed_project_ids == []
    assert policy.can_read_private_doc_ids == []
    assert policy.milvus_filter == ""


def test_query_rewrite_result_defaults() -> None:
    result = QueryRewriteResult(original_query="test")
    assert result.original_query == "test"
    assert result.rewritten_query == ""
    assert result.keywords == []
    assert result.strategy == "light_rewrite"
    assert result.retry_count == 0


def test_citation_item() -> None:
    item = CitationItem(doc_id="doc-1", source_file="a.pdf")
    assert item.doc_id == "doc-1"
    assert item.source_file == "a.pdf"


def test_retrieval_debug_trace_defaults() -> None:
    trace = RetrievalDebugTrace()
    assert trace.profile == RetrievalProfile.STANDARD
    assert trace.bias_mode == BiasMode.BALANCED
    assert trace.low_confidence is False
    assert trace.low_recall is False
    assert trace.rewrite_retry_count == 0


def test_access_audit_log_defaults() -> None:
    log = AccessAuditLog()
    assert log.user_id == ""
    assert log.blocked_doc_ids == []
    assert log.deny_reason == ""


def test_knowledge_answer_payload_defaults() -> None:
    payload = KnowledgeAnswerPayload()
    assert payload.answer == ""
    assert payload.citations == []
    assert payload.retrieval_debug.profile == RetrievalProfile.STANDARD


def test_knowledge_answer_payload_serialization() -> None:
    payload = KnowledgeAnswerPayload(
        answer="test answer",
        citations=[CitationItem(doc_id="doc-1", source_file="a.pdf")],
    )
    data = payload.model_dump()
    assert data["answer"] == "test answer"
    assert len(data["citations"]) == 1
