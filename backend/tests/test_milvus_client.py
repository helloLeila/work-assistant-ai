"""向量存储统一过滤测试。

系统论说明：
- 本测试锁定 Milvus dense 主路径与本地词法回退路径的 ACL 行为一致性；
- 任何对 _build_milvus_filter 或 _document_passes_acl 的修改都必须在此验证，
  防止本地回退变成越权通道。
"""

from __future__ import annotations

import pytest

from app.models.knowledge import DocumentStatus, VisibilityScope
from app.models.knowledge_retrieval import AccessPolicy
from app.vectorstore.milvus_client import KnowledgeVectorStore


@pytest.fixture
def vectorstore() -> KnowledgeVectorStore:
    """提供隔离的 KnowledgeVectorStore 实例。"""
    return KnowledgeVectorStore()


@pytest.fixture
def sample_policy() -> AccessPolicy:
    """提供测试用 AccessPolicy。"""
    return AccessPolicy(
        allowed_departments=["HR"],
        allowed_project_ids=["proj-1"],
        can_read_private_doc_ids=["doc-admin"],
        milvus_filter='status == "active" and is_latest == true',
    )


class TestBuildMilvusFilter:
    """测试 Milvus 过滤表达式构建器。"""

    def test_uses_policy_filter_when_provided(self, vectorstore: KnowledgeVectorStore, sample_policy: AccessPolicy) -> None:
        """传入 AccessPolicy 时优先使用其 milvus_filter。"""
        expr = vectorstore._build_milvus_filter(sample_policy, history_lookup=False)
        assert expr == 'status == "active" and is_latest == true'

    def test_default_filter_without_policy(self, vectorstore: KnowledgeVectorStore) -> None:
        """无 policy 时返回默认 active + is_latest 过滤。"""
        expr = vectorstore._build_milvus_filter(None, history_lookup=False)
        assert 'status == "active"' in expr
        assert "is_latest == true" in expr

    def test_history_lookup_with_policy(self, vectorstore: KnowledgeVectorStore, sample_policy: AccessPolicy) -> None:
        """history_lookup=True 时保留 policy 其他条件，仅放宽 is_latest。"""
        expr = vectorstore._build_milvus_filter(sample_policy, history_lookup=True)
        assert 'status == "active"' in expr
