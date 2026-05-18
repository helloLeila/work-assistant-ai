"""企业检索配置项测试。"""

from __future__ import annotations

from app.core.config import Settings


def test_rag_config_defaults(monkeypatch) -> None:
    """RAG 核心配置默认值应符合设计文档。"""
    settings = Settings(_env_file=None)

    assert settings.knowledge_chunk_size == 512
    assert settings.knowledge_chunk_overlap == 128
    assert settings.knowledge_rewrite_retry_max == 1
    assert settings.knowledge_rrf_rank_constant == 60
    assert settings.knowledge_rerank_top_k == 5
    assert settings.knowledge_rerank_input_max == 50
    assert settings.knowledge_rerank_input_high_recall_max == 80
    assert settings.knowledge_retrieval_profile == "standard"
    assert settings.knowledge_bias_mode == "balanced"
    assert settings.knowledge_low_recall_threshold == 5
    assert settings.knowledge_low_confidence_threshold == 3
    assert settings.knowledge_history_lookup_enabled is True
    assert settings.retrieval_debug_trace_retention_days == 7
    assert settings.access_audit_log_retention_days == 180
    assert settings.user_behavior_log_retention_days == 30
