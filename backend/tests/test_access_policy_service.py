"""访问策略服务测试。"""

from __future__ import annotations

from app.core.security import CurrentUser
from app.models.knowledge import DocumentStatus, VisibilityScope
from app.models.knowledge_retrieval import AccessPolicy
from app.services.access_policy_service import (
    build_local_acl_filter,
    chunk_should_be_visible,
    has_project_ids_support,
    resolve_access_policy,
)


def _make_user(
    *,
    user_id: str = "u-001",
    username: str = "test",
    name: str = "Test",
    role: str = "employee",
    department: str = "HR",
    manager_id: str | None = None,
) -> CurrentUser:
    return CurrentUser(
        sub=user_id,
        username=username,
        name=name,
        role=role,
        department=department,
        manager_id=manager_id,
    )


def test_has_project_ids_support_false() -> None:
    user = _make_user()
    assert has_project_ids_support(user) is False


def test_resolve_public_visibility() -> None:
    user = _make_user(role="employee", department="HR")
    policy = resolve_access_policy(user)
    assert isinstance(policy, AccessPolicy)
    assert f'status == "{DocumentStatus.ACTIVE.value}"' in policy.milvus_filter
    assert "is_latest == true" in policy.milvus_filter
    assert "visibility_scope" in policy.milvus_filter


def test_resolve_admin_can_see_all() -> None:
    user = _make_user(role="knowledge_admin", department="HR")
    docs = [
        {"doc_id": "doc-1", "visibility_scope": VisibilityScope.PRIVATE.value},
        {"doc_id": "doc-2", "visibility_scope": VisibilityScope.PUBLIC.value},
    ]
    policy = resolve_access_policy(user, all_documents=docs)
    assert "doc-1" in policy.can_read_private_doc_ids
    assert "doc-2" not in policy.can_read_private_doc_ids


def test_resolve_department_filter() -> None:
    user = _make_user(role="employee", department="Finance")
    policy = resolve_access_policy(user)
    assert "Finance" in policy.allowed_departments
    assert 'department == "Finance"' in policy.milvus_filter


def test_project_scope_disabled_without_project_ids() -> None:
    user = _make_user(role="employee", department="HR")
    policy = resolve_access_policy(user)
    # project_ids 未就绪时，不应在 filter 中出现 project 相关条件
    assert "project_ids" not in policy.milvus_filter or policy.allowed_project_ids == []


def test_history_lookup_removes_is_latest() -> None:
    user = _make_user(role="employee", department="HR")
    policy = resolve_access_policy(user, history_lookup=True)
    assert "is_latest == true" not in policy.milvus_filter


def test_build_local_acl_filter() -> None:
    user = _make_user(role="employee", department="HR")
    filt = build_local_acl_filter(user)
    assert filt["allowed_departments"] == ["HR"]
    assert filt["is_admin"] is False
    assert filt["user_id"] == "u-001"


def test_chunk_visibility_public() -> None:
    user = _make_user(role="employee", department="HR")
    policy = resolve_access_policy(user)
    assert chunk_should_be_visible({"visibility_scope": "public"}, policy, user) is True


def test_chunk_visibility_department_match() -> None:
    user = _make_user(role="employee", department="HR")
    policy = resolve_access_policy(user)
    assert (
        chunk_should_be_visible(
            {"visibility_scope": "department", "department": "HR"},
            policy,
            user,
        )
        is True
    )


def test_chunk_visibility_department_mismatch() -> None:
    user = _make_user(role="employee", department="HR")
    policy = resolve_access_policy(user)
    assert (
        chunk_should_be_visible(
            {"visibility_scope": "department", "department": "Finance"},
            policy,
            user,
        )
        is False
    )


def test_chunk_visibility_private_admin() -> None:
    user = _make_user(role="knowledge_admin", department="HR")
    policy = resolve_access_policy(user)
    assert (
        chunk_should_be_visible(
            {"visibility_scope": "private", "owner_user_id": "other"},
            policy,
            user,
        )
        is True
    )


def test_chunk_visibility_private_owner() -> None:
    user = _make_user(role="employee", department="HR", user_id="u-001")
    policy = resolve_access_policy(user)
    assert (
        chunk_should_be_visible(
            {"visibility_scope": "private", "owner_user_id": "u-001"},
            policy,
            user,
        )
        is True
    )


def test_chunk_visibility_private_other() -> None:
    user = _make_user(role="employee", department="HR", user_id="u-001")
    policy = resolve_access_policy(user)
    assert (
        chunk_should_be_visible(
            {"visibility_scope": "private", "owner_user_id": "u-002"},
            policy,
            user,
        )
        is False
    )
