"""检索审计服务测试。

本测试锁定 RetrievalAuditService 的审计日志生成行为：
- log_access 必须返回 AccessAuditLog 类型；
- 用户身份、请求上下文、匹配/阻挡文档应完整记录；
- 查询含敏感信息（身份证号、手机号、工号）时必须脱敏；
- 未提供的字段应使用安全默认值。

任何对审计逻辑或脱敏规则的调整都必须在此验证，防止敏感信息泄露。
"""

from __future__ import annotations

import pytest

from app.models.knowledge_retrieval import AccessAuditLog
from app.services.retrieval_audit_service import (
    RetrievalAuditService,
    _mask_sensitive_query,
)


@pytest.fixture
def service() -> RetrievalAuditService:
    """提供隔离的 RetrievalAuditService 实例。"""
    return RetrievalAuditService()


class TestLogAccess:
    """测试审计日志基础字段记录。"""

    def test_returns_typed_log(self, service: RetrievalAuditService) -> None:
        """log_access 必须返回 AccessAuditLog 类型。"""
        log = service.log_access(query="test")
        assert isinstance(log, AccessAuditLog)

    def test_records_user_and_roles(self, service: RetrievalAuditService) -> None:
        """用户 ID 与角色列表应完整透传。"""
        log = service.log_access(
            user_id="user-123",
            user_roles=["employee", "knowledge_admin"],
            query="test",
        )
        assert log.user_id == "user-123"
        assert log.user_roles == ["employee", "knowledge_admin"]

    def test_records_client_ip(self, service: RetrievalAuditService) -> None:
        """客户端 IP 应被记录。"""
        log = service.log_access(
            client_ip="192.168.1.10",
            query="test",
        )
        assert log.client_ip == "192.168.1.10"

    def test_records_matched_and_blocked_docs(
        self, service: RetrievalAuditService
    ) -> None:
        """匹配文档与被阻挡文档应分别记录。"""
        log = service.log_access(
            query="test",
            matched_doc_ids=["doc-1", "doc-2"],
            blocked_doc_ids=["doc-3"],
        )
        assert log.matched_doc_ids == ["doc-1", "doc-2"]
        assert log.blocked_doc_ids == ["doc-3"]

    def test_records_deny_reason(self, service: RetrievalAuditService) -> None:
        """拦截原因应被记录。"""
        log = service.log_access(
            query="test",
            deny_reason="private doc, not owner",
        )
        assert log.deny_reason == "private doc, not owner"


class TestQueryMasking:
    """测试敏感查询脱敏。"""

    def test_masks_id_card(self, service: RetrievalAuditService) -> None:
        """18位身份证号应被整体替换为等长星号。"""
        log = service.log_access(
            query="员工 110101199001011234 的报销政策",
        )
        assert "110101199001011234" not in log.query
        assert "******************" in log.query
        assert "员工" in log.query
        assert "的报销政策" in log.query

    def test_masks_phone_number(self, service: RetrievalAuditService) -> None:
        """11位手机号应被整体替换为等长星号。"""
        log = service.log_access(
            query="联系人 13800138000 的合同在哪里",
        )
        assert "13800138000" not in log.query
        assert "***********" in log.query
        assert "联系人" in log.query

    def test_masks_employee_id(self, service: RetrievalAuditService) -> None:
        """4位以上连续数字（工号）应被替换为等长星号。"""
        log = service.log_access(
            query="员工 12345 的考勤记录",
        )
        assert "12345" not in log.query
        assert "*****" in log.query
        assert "员工" in log.query
        assert "的考勤记录" in log.query

    def test_masks_multiple_sensitives(self, service: RetrievalAuditService) -> None:
        """单条查询含多处敏感信息时应全部脱敏。"""
        log = service.log_access(
            query="员工 12345 手机 13800138000",
        )
        assert "12345" not in log.query
        assert "13800138000" not in log.query

    def test_no_mask_for_normal_query(self, service: RetrievalAuditService) -> None:
        """不含敏感信息的查询应保持原样。"""
        log = service.log_access(
            query="年假怎么休",
        )
        assert log.query == "年假怎么休"

    def test_mask_function_directly(self) -> None:
        """_mask_sensitive_query 对纯数字长串做脱敏。"""
        result = _mask_sensitive_query("编号 12345678 结束")
        assert "12345678" not in result
        assert "编号" in result
        assert "结束" in result


class TestDefaults:
    """测试默认值安全性。"""

    def test_defaults_when_minimal_args(self, service: RetrievalAuditService) -> None:
        """仅提供 query 时其余字段使用安全默认值。"""
        log = service.log_access(query="test")
        assert log.user_id == ""
        assert log.user_roles == []
        assert log.client_ip == ""
        assert log.matched_doc_ids == []
        assert log.blocked_doc_ids == []
        assert log.deny_reason == ""

    def test_none_lists_default_to_empty(self, service: RetrievalAuditService) -> None:
        """显式传入 None 作为列表时应回退为空列表。"""
        log = service.log_access(
            query="test",
            user_roles=None,
            matched_doc_ids=None,
            blocked_doc_ids=None,
        )
        assert log.user_roles == []
        assert log.matched_doc_ids == []
        assert log.blocked_doc_ids == []

    def test_auto_timestamps(self, service: RetrievalAuditService) -> None:
        """未提供 request_start/request_end 时应自动填充当前 UTC 时间。"""
        log = service.log_access(query="test")
        assert log.request_start
        assert log.request_end
        assert log.timestamp
        # 三者应为有效的 ISO 格式字符串
        assert "T" in log.timestamp
        assert "+00:00" in log.timestamp or "Z" in log.timestamp
