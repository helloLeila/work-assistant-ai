"""检索审计日志服务。

本服务位于企业 RAG 检索链路的安全合规层，对应检索流程中的审计阶段。
上游由 run_retrieval_pipeline 或 API 路由在每次检索请求后调用；
下游把 AccessAuditLog 写入日志系统（如 ELK / Loki / 本地 JSONL），
供安全审计、合规审查与异常行为分析使用。

核心职责：
1. 记录用户身份（user_id、user_roles）与请求上下文（client_ip、query）；
2. 记录匹配到的文档（matched_doc_ids）与被阻挡的文档（blocked_doc_ids）；
3. 记录拒绝原因（deny_reason），用于 ACL 拦截追溯；
4. 对查询中的敏感信息（身份证号、手机号、工号等）做自动脱敏；
5. 为每条记录附加 UTC 时间戳（request_start、request_end、timestamp）。

关联模型：
- AccessAuditLog（backend/app/models/knowledge_retrieval.py）：统一审计日志结构。

调用方：
- API 路由或 run_retrieval_pipeline 在检索请求完成后调用 log_access，
  把结果存入日志系统；未来可扩展为异步批量写入，降低对主链路的延迟影响。
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from app.models.knowledge_retrieval import AccessAuditLog


# 敏感信息正则模式：身份证号、手机号、工号（4位以上连续数字）
# 命中后统一替换为等长星号，保留非敏感部分供审计人员判断查询意图
_SENSITIVE_PATTERNS = [
    re.compile(r"\d{18}"),          # 18位身份证号
    re.compile(r"1[3-9]\d{9}"),     # 11位手机号
    re.compile(r"[A-Z]?\d{4,}"),    # 4位以上数字，可能带前缀字母（工号、合同号）
]


def _mask_sensitive_query(query: str) -> str:
    """对查询中的敏感信息做脱敏处理。

    脱敏规则：
    - 身份证号（18位数字）整体替换为等长星号；
    - 手机号（11位，1开头）整体替换为等长星号；
    - 工号/合同号（4位以上连续数字，可能带前缀字母）整体替换为等长星号。

    参数：
    - query: 用户原始查询字符串。

    返回值：
    脱敏后的查询字符串，敏感部分被等长星号替代，非敏感文本保持不变。
    """
    masked = query
    for pattern in _SENSITIVE_PATTERNS:
        masked = pattern.sub(lambda m: "*" * len(m.group()), masked)
    return masked


class RetrievalAuditService:
    """检索审计服务。

    职责定位：
    位于 RAG 检索链路的安全合规层，不介入检索逻辑本身，只负责在检索请求
    完成后生成标准化的审计日志，满足企业安全审计与数据合规要求。

    上下游关联：
    - 上游调用方：API 路由（backend/app/api/routes/knowledge.py）或
      run_retrieval_pipeline（backend/app/chains/rag_chain.py）在请求完成后调用；
    - 下游消费方：AccessAuditLog 被写入日志系统，供安全团队审计与合规审查。
    """

    def log_access(
        self,
        *,
        user_id: str = "",
        user_roles: list[str] | None = None,
        client_ip: str = "",
        query: str = "",
        matched_doc_ids: list[str] | None = None,
        blocked_doc_ids: list[str] | None = None,
        deny_reason: str = "",
        request_start: str = "",
        request_end: str = "",
    ) -> AccessAuditLog:
        """生成单次检索请求的审计日志。

        本函数在检索请求完成后调用，把请求上下文、用户身份、匹配结果与
        阻挡信息封装为 AccessAuditLog。查询字符串会经过 _mask_sensitive_query
        自动脱敏，防止敏感个人信息进入日志系统。

        参数说明：
        - user_id: 发起请求的用户标识；
        - user_roles: 用户角色列表（如 ["employee", "hr_admin"]）；
        - client_ip: 客户端 IP 地址；
        - query: 用户原始查询字符串（会自动脱敏）；
        - matched_doc_ids: 本次检索命中的文档 ID 列表；
        - blocked_doc_ids: 被 ACL 拦截的文档 ID 列表；
        - deny_reason: 拦截原因描述（如 "private doc, not owner"）；
        - request_start: 请求开始时间（ISO 格式字符串），为空时自动填充当前时间；
        - request_end: 请求结束时间（ISO 格式字符串），为空时自动填充当前时间。

        返回值：
        AccessAuditLog 对象，可直接序列化为 JSON 后写入日志系统。
        """
        now = datetime.now(timezone.utc).isoformat()
        masked_query = _mask_sensitive_query(query)

        return AccessAuditLog(
            user_id=user_id,
            user_roles=user_roles or [],
            client_ip=client_ip,
            query=masked_query,
            matched_doc_ids=matched_doc_ids or [],
            blocked_doc_ids=blocked_doc_ids or [],
            deny_reason=deny_reason,
            request_start=request_start or now,
            request_end=request_end or now,
            timestamp=now,
        )
