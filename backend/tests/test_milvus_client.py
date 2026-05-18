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


class TestDocumentPassesAcl:
    """测试本地回退路径的 ACL 核心安全检查点。"""

    def test_public_always_visible(self, vectorstore: KnowledgeVectorStore, sample_policy: AccessPolicy) -> None:
        """public 文档在无权限限制时始终可见。"""
        meta = {"visibility_scope": VisibilityScope.PUBLIC.value}
        assert vectorstore._document_passes_acl(meta, sample_policy) is True

    def test_department_match(self, vectorstore: KnowledgeVectorStore, sample_policy: AccessPolicy) -> None:
        """department 匹配时可见。"""
        meta = {"visibility_scope": VisibilityScope.DEPARTMENT.value, "department": "HR"}
        assert vectorstore._document_passes_acl(meta, sample_policy) is True

    def test_department_mismatch_blocked(self, vectorstore: KnowledgeVectorStore, sample_policy: AccessPolicy) -> None:
        """department 不匹配时被过滤。"""
        meta = {"visibility_scope": VisibilityScope.DEPARTMENT.value, "department": "Finance"}
        assert vectorstore._document_passes_acl(meta, sample_policy) is False

    def test_private_owner_match(self, vectorstore: KnowledgeVectorStore) -> None:
        """private 文档 owner 匹配时可见。"""
        policy = AccessPolicy(
            allowed_departments=["HR"],
            allowed_project_ids=[],
            can_read_private_doc_ids=[],
            milvus_filter='status == "active"',
            user_id="u-001",
        )
        meta = {"visibility_scope": VisibilityScope.PRIVATE.value, "owner_user_id": "u-001"}
        assert vectorstore._document_passes_acl(meta, policy, history_lookup=False) is True

    def test_private_other_blocked(self, vectorstore: KnowledgeVectorStore) -> None:
        """private 文档 owner 不匹配且无 admin 权限时被过滤。"""
        policy = AccessPolicy(
            allowed_departments=["HR"],
            allowed_project_ids=[],
            can_read_private_doc_ids=[],
            milvus_filter='status == "active"',
            user_id="u-001",
        )
        meta = {"visibility_scope": VisibilityScope.PRIVATE.value, "owner_user_id": "u-002", "doc_id": "doc-other"}
        assert vectorstore._document_passes_acl(meta, policy, history_lookup=False) is False

    def test_admin_private_visible(self, vectorstore: KnowledgeVectorStore, sample_policy: AccessPolicy) -> None:
        """admin 通过 can_read_private_doc_ids 可查看 private 文档。"""
        meta = {"visibility_scope": VisibilityScope.PRIVATE.value, "doc_id": "doc-admin", "owner_user_id": "other"}
        assert vectorstore._document_passes_acl(meta, sample_policy, history_lookup=False) is True

    def test_deprecated_blocked_by_default(self, vectorstore: KnowledgeVectorStore) -> None:
        """默认过滤排除 deprecated 状态文档。"""
        meta = {"status": DocumentStatus.DEPRECATED.value, "is_latest": True}
        assert vectorstore._document_passes_acl(meta, None, history_lookup=False) is False

    def test_non_latest_blocked_by_default(self, vectorstore: KnowledgeVectorStore) -> None:
        """默认过滤排除非最新版本。"""
        meta = {"status": DocumentStatus.ACTIVE.value, "is_latest": False}
        assert vectorstore._document_passes_acl(meta, None, history_lookup=False) is False
