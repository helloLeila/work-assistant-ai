"""访问策略服务。

把"当前用户能看什么"转成统一检索过滤条件，保证三套链路（dense/sparse/本地回退）
复用同一个 AccessPolicy，不允许各写一套过滤逻辑。
"""

from __future__ import annotations

from typing import Any

from app.core.config import get_settings
from app.core.security import CurrentUser
from app.models.knowledge import DocumentStatus, VisibilityScope
from app.models.knowledge_retrieval import AccessPolicy


# 一期默认允许的管理员角色
_ADMIN_ROLES = {"hr_admin", "knowledge_admin"}


def has_project_ids_support(user: CurrentUser) -> bool:
    """判断当前用户模型是否已具备 project_ids 字段。

    project_ids 未就绪时，project scope 必须显式降级为不启用。
    """
    # 通过 model_extra / 字典形式检查，避免 model 定义变更前硬引用不存在的字段
    raw = user.model_dump(mode="json")
    return "project_ids" in raw and bool(raw["project_ids"])


def resolve_access_policy(
    user: CurrentUser,
    *,
    all_documents: list[dict[str, Any]] | None = None,
    history_lookup: bool = False,
) -> AccessPolicy:
    """把用户上下文解析为统一 AccessPolicy。

    参数:
        user: 当前用户上下文。
        all_documents: 全部文档 metadata 列表，用于计算管理员可访问的 private 文档。
        history_lookup: 是否开启历史版本查询模式；为 True 时放宽 is_latest 过滤。
    """
    settings = get_settings()
    is_admin = user.role in _ADMIN_ROLES

    allowed_departments: list[str] = []
    allowed_project_ids: list[str] = []
    can_read_private_doc_ids: list[str] = []

    # public：所有登录用户都可见，不需要额外过滤条件

    # department：仅用户所在部门
    if user.department:
        allowed_departments.append(user.department)

    # project：仅在用户模型已具备 project_ids 时才启用
    if has_project_ids_support(user):
        raw = user.model_dump(mode="json")
        allowed_project_ids = list(raw.get("project_ids", []))

    # private：管理员可查看全部 private 文档
    if is_admin and all_documents is not None:
        can_read_private_doc_ids = [
            str(doc["doc_id"])
            for doc in all_documents
            if doc.get("visibility_scope") == VisibilityScope.PRIVATE.value
        ]
    elif not is_admin:
        # 普通用户只能看自己拥有的 private 文档
        # 通过 owner_user_id 匹配 user_id
        pass  # milvus_filter 中通过 owner_user_id 表达式处理

    # 构建 Milvus filter 表达式
    filter_parts: list[str] = []

    # 状态过滤：默认只检索 active
    filter_parts.append(f'status == "{DocumentStatus.ACTIVE.value}"')

    # 版本过滤：默认只检索最新版本
    if not history_lookup:
        filter_parts.append("is_latest == true")

    # 可见范围过滤
    scope_conditions: list[str] = []
    scope_conditions.append(f'visibility_scope == "{VisibilityScope.PUBLIC.value}"')

    if allowed_departments:
        dept_expr = " or ".join(f'department == "{d}"' for d in allowed_departments)
        scope_conditions.append(
            f'(visibility_scope == "{VisibilityScope.DEPARTMENT.value}" and ({dept_expr}))'
        )

    if allowed_project_ids:
        proj_expr = " or ".join(f'"{p}" in project_ids' for p in allowed_project_ids)
        scope_conditions.append(
            f'(visibility_scope == "{VisibilityScope.PROJECT.value}" and ({proj_expr}))'
        )

    # private 文档过滤
    private_conditions: list[str] = []
    if can_read_private_doc_ids:
        ids_expr = " or ".join(f'doc_id == "{d}"' for d in can_read_private_doc_ids)
        private_conditions.append(f'({ids_expr})')
    if not is_admin:
        # 普通用户只能看自己的 private 文档
        private_conditions.append(f'owner_user_id == "{user.user_id}"')

    if private_conditions:
        private_expr = " or ".join(private_conditions)
        scope_conditions.append(
            f'(visibility_scope == "{VisibilityScope.PRIVATE.value}" and ({private_expr}))'
        )
    else:
        # 没有任何 private 权限时，排除所有 private 文档
        scope_conditions.append(f'visibility_scope != "{VisibilityScope.PRIVATE.value}"')

    scope_filter = " or ".join(scope_conditions)
    filter_parts.append(f"({scope_filter})")

    # 有效期过滤：effective_at <= now 且 (expires_at 为空 或 expires_at > now)
    # 由于 Milvus 不支持复杂日期比较，首版在应用层做二次过滤，
    # filter 中只保留简单表达式，日期精确过滤在 retrieval_pipeline 中处理。

    milvus_filter = " and ".join(filter_parts)

    return AccessPolicy(
        allowed_departments=allowed_departments,
        allowed_project_ids=allowed_project_ids,
        can_read_private_doc_ids=can_read_private_doc_ids,
        milvus_filter=milvus_filter,
    )


def build_local_acl_filter(user: CurrentUser, is_admin: bool = False) -> dict[str, Any]:
    """为本地词法回退路径构建 ACL 过滤字典，与 AccessPolicy 语义一致。"""
    allowed_departments: list[str] = []
    if user.department:
        allowed_departments.append(user.department)

    allowed_project_ids: list[str] = []
    if has_project_ids_support(user):
        raw = user.model_dump(mode="json")
        allowed_project_ids = list(raw.get("project_ids", []))

    return {
        "allowed_departments": allowed_departments,
        "allowed_project_ids": allowed_project_ids,
        "is_admin": is_admin or user.role in _ADMIN_ROLES,
        "user_id": user.user_id,
    }


def chunk_should_be_visible(
    chunk_meta: dict[str, Any],
    policy: AccessPolicy,
    user: CurrentUser,
) -> bool:
    """判断单个 chunk 是否对用户可见（用于本地回退路径二次确认）。"""
    scope = chunk_meta.get("visibility_scope", VisibilityScope.PUBLIC.value)
    if scope == VisibilityScope.PUBLIC.value:
        return True
    if scope == VisibilityScope.DEPARTMENT.value:
        return chunk_meta.get("department") in policy.allowed_departments
    if scope == VisibilityScope.PROJECT.value:
        if not has_project_ids_support(user):
            return False
        raw = user.model_dump(mode="json")
        user_projects = set(raw.get("project_ids", []))
        doc_projects = set(chunk_meta.get("project_ids", []))
        return bool(user_projects & doc_projects)
    if scope == VisibilityScope.PRIVATE.value:
        is_admin = user.role in _ADMIN_ROLES
        if is_admin:
            return True
        return chunk_meta.get("owner_user_id") == user.user_id
    return False
