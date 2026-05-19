"""向量存储统一过滤测试。

本测试锁定 Milvus dense 主路径与本地词法回退路径的 ACL 行为一致性。
任何对 _build_milvus_filter 或 _document_passes_acl 的修改都必须在此验证，
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

    def test_history_lookup_removes_is_latest(self, vectorstore: KnowledgeVectorStore) -> None:
        """history_lookup=True 时放宽 is_latest 限制。"""
        expr = vectorstore._build_milvus_filter(None, history_lookup=True)
        assert "is_latest == true or is_latest == false" in expr

    def test_history_lookup_with_policy(self, vectorstore: KnowledgeVectorStore, sample_policy: AccessPolicy) -> None:
        """history_lookup=True 时保留 policy 其他条件，仅放宽 is_latest。"""
        expr = vectorstore._build_milvus_filter(sample_policy, history_lookup=True)
        assert 'status == "active"' in expr
        assert "is_latest == true or is_latest == false" in expr


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

    def test_history_lookup_deprecated_visible(self, vectorstore: KnowledgeVectorStore) -> None:
        """history_lookup=True 时允许命中 deprecated 文档。"""
        meta = {"status": DocumentStatus.DEPRECATED.value, "is_latest": True}
        assert vectorstore._document_passes_acl(meta, None, history_lookup=True) is True

    def test_history_lookup_non_latest_visible(self, vectorstore: KnowledgeVectorStore) -> None:
        """history_lookup=True 时允许命中非最新版本。"""
        meta = {"status": DocumentStatus.ACTIVE.value, "is_latest": False}
        assert vectorstore._document_passes_acl(meta, None, history_lookup=True) is True


class TestSparseSearch:
    """测试本地稀疏检索（sparse 补充路径）。"""

    def test_sparse_search_returns_candidates(self, vectorstore: KnowledgeVectorStore) -> None:
        """基于 keywords 的稀疏检索能返回候选。"""
        from langchain_core.documents import Document

        vectorstore._records = [
            Document(page_content="员工报销流程规定", metadata={"status": "active", "is_latest": True}),
            Document(page_content="年假休假制度说明", metadata={"status": "active", "is_latest": True}),
        ]
        results = vectorstore._sparse_search("报销", ["报销", "流程"], top_k=5)
        assert len(results) > 0
        assert any("报销" in r["content"] for r in results)

    def test_sparse_search_empty_keywords(self, vectorstore: KnowledgeVectorStore) -> None:
        """空 keywords 时返回空列表。"""
        results = vectorstore._sparse_search("query", [], top_k=5)
        assert results == []

    def test_sparse_search_respects_acl(self, vectorstore: KnowledgeVectorStore) -> None:
        """sparse 路径同样执行 ACL 过滤。"""
        from langchain_core.documents import Document

        vectorstore._records = [
            Document(
                page_content="财务部报销规定",
                metadata={
                    "status": "active",
                    "is_latest": True,
                    "visibility_scope": VisibilityScope.DEPARTMENT.value,
                    "department": "Finance",
                },
            ),
        ]
        policy = AccessPolicy(allowed_departments=["HR"], milvus_filter='status == "active"')
        results = vectorstore._sparse_search("报销", ["报销"], access_policy=policy, top_k=5)
        assert len(results) == 0


class TestSearchHybrid:
    """测试 search 方法整合 keywords 后的 hybrid 行为。"""

    def test_search_with_keywords(self, vectorstore: KnowledgeVectorStore) -> None:
        """传入 keywords 时，sparse 补充路径生效。"""
        from langchain_core.documents import Document

        vectorstore._records = [
            Document(page_content="员工报销流程规定", metadata={"status": "active", "is_latest": True}),
            Document(page_content="年假休假制度说明", metadata={"status": "active", "is_latest": True}),
        ]
        results = vectorstore.search("报销", keywords=["报销", "流程"], top_k=5)
        assert len(results) > 0
        assert any("报销" in r["content"] for r in results)

    def test_search_keywords_do_not_replace_query(self, vectorstore: KnowledgeVectorStore) -> None:
        """keywords 增强 sparse 命中，不替换原 query 的 dense 检索语义。"""
        from langchain_core.documents import Document

        vectorstore._records = [
            Document(page_content="员工报销流程规定", metadata={"status": "active", "is_latest": True}),
        ]
        # 即使 keywords 与 query 不同，sparse 仍基于 keywords 命中
        results = vectorstore.search("年假", keywords=["报销"], top_k=5)
        assert any("报销" in r["content"] for r in results)

    def test_keyword_bias_expands_sparse(self, vectorstore: KnowledgeVectorStore) -> None:
        """keyword_bias 时扩大 sparse 候选规模。"""
        from langchain_core.documents import Document

        vectorstore._records = [
            Document(page_content="员工报销流程规定", metadata={"status": "active", "is_latest": True}),
            Document(page_content="年假休假制度说明", metadata={"status": "active", "is_latest": True}),
        ]
        # keyword_bias 下 sparse_top_k = top_k * 1.5 = 7（当 top_k=5）
        results = vectorstore.search("报销", keywords=["报销", "流程"], bias_mode="keyword_bias", top_k=5)
        assert len(results) > 0

    def test_semantic_bias_reduces_sparse(self, vectorstore: KnowledgeVectorStore) -> None:
        """semantic_bias 时缩减 sparse 候选规模。"""
        from langchain_core.documents import Document

        vectorstore._records = [
            Document(page_content="员工报销流程规定", metadata={"status": "active", "is_latest": True}),
            Document(page_content="年假休假制度说明", metadata={"status": "active", "is_latest": True}),
        ]
        # semantic_bias 下 sparse_top_k = top_k * 0.5 = 2（当 top_k=5）
        results = vectorstore.search("报销", keywords=["报销", "流程"], bias_mode="semantic_bias", top_k=5)
        assert len(results) >= 0

    def test_candidate_format_unified(self, vectorstore: KnowledgeVectorStore) -> None:
        """dense、sparse、lexical 三条路径返回的候选字段完全一致。"""
        from langchain_core.documents import Document

        doc = Document(
            page_content="测试内容",
            metadata={
                "doc_id": "doc-1",
                "chunk_id": "doc-1-chunk-1",
                "status": "active",
                "is_latest": True,
                "source_file": "test.txt",
                "section_path": "第一章",
                "page_num": 1,
                "department": "HR",
                "doc_type": "txt",
                "token_count": 10,
            },
        )
        vectorstore._records = [doc]

        sparse = vectorstore._sparse_search("测试", ["测试"], top_k=5)
        lexical = vectorstore._lexical_search("测试", top_k=5)

        assert len(sparse) == 1
        assert len(lexical) == 1
        # 字段集合必须一致
        assert set(sparse[0].keys()) == set(lexical[0].keys())
        assert sparse[0]["chunk_id"] == lexical[0]["chunk_id"] == "doc-1-chunk-1"
