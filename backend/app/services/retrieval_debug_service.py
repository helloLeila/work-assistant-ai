"""检索调试日志服务。

本服务位于企业 RAG 检索链路的观测层，对应 RAG 流程中的 Debug Trace 阶段。
上游由 run_retrieval_pipeline 在各阶段调用，接收 rewrite、retrieval、rerank
的中间结果；下游把 RetrievalDebugTrace 写入日志或返回给调用方，供排障与链路
还原使用。

核心职责：
1. 把 retrieval_pipeline 各阶段中间结果封装为 RetrievalDebugTrace；
2. 记录 dense/sparse/RRF/rerank 的分数与候选列表（若调用方提供）；
3. 记录改写重试次数、fallback 触发动作、history_lookup 状态等元信息；
4. 为所有字段提供类型安全的默认值，防止排障时因字段缺失导致解析失败。

关联模型：
- RetrievalDebugTrace（backend/app/models/knowledge_retrieval.py）：统一输出结构；
- RetrievalProfile / BiasMode：profile 与偏向模式枚举。

调用方：
- run_retrieval_pipeline（backend/app/chains/rag_chain.py）在检索链路末尾调用
  build_trace，把各阶段结果汇总后写入 KnowledgeAnswerPayload.retrieval_debug。
"""

from __future__ import annotations

from typing import Any

from app.models.knowledge_retrieval import (
    BiasMode,
    RetrievalDebugTrace,
    RetrievalProfile,
)


class RetrievalDebugService:
    """检索调试服务。

    职责定位：
    位于 RAG 检索链路的观测层，不介入检索逻辑本身，只负责把各阶段中间结果
    封装为标准化的 RetrievalDebugTrace，供日志、排障、链路还原使用。

    上下游关联：
    - 上游调用方：rag_chain.run_retrieval_pipeline 在检索链路末尾调用 build_trace；
    - 下游消费方：KnowledgeAnswerPayload.retrieval_debug 被 API 路由返回给前端，
      也可被后台日志系统采集后写入 ELK / Loki 等日志平台。
    """

    def build_trace(
        self,
        *,
        original_query: str,
        rewritten_query: str = "",
        acl_filter: str = "",
        profile: RetrievalProfile = RetrievalProfile.STANDARD,
        bias_mode: BiasMode = BiasMode.BALANCED,
        dense_candidates: list[dict[str, Any]] | None = None,
        sparse_candidates: list[dict[str, Any]] | None = None,
        rrf_merged: list[dict[str, Any]] | None = None,
        reranked_top: list[dict[str, Any]] | None = None,
        low_recall: bool = False,
        low_confidence: bool = False,
        rewrite_retry_count: int = 0,
        fallback_triggered: str = "",
        history_lookup: bool = False,
    ) -> RetrievalDebugTrace:
        """封装各阶段中间结果为 RetrievalDebugTrace。

        本函数把 retrieval_pipeline 各阶段的中间结果聚合为一个标准化的调试追踪
        对象。所有参数均为可选（有默认值），允许调用方在不同阶段逐步填充。

        参数说明：
        - original_query: 用户原始查询字符串；
        - rewritten_query: 改写后的查询字符串（由 QueryRewriteService 输出）；
        - acl_filter: ACL 过滤表达式或描述字符串（由 AccessPolicyResolver 输出）；
        - profile: 当前检索档位，默认 STANDARD；
        - bias_mode: 检索偏向模式，默认 BALANCED；
        - dense_candidates: 稠密检索候选列表（含 score），由 Milvus dense 路径输出；
        - sparse_candidates: 稀疏检索候选列表（含 score），由 BM25/sparse 路径输出；
        - rrf_merged: RRF 融合后的候选列表，由 _rrf_merge 输出；
        - reranked_top: rerank 精排后的 Top-K 候选，由 RerankService 输出；
        - low_recall: 是否判定为低召回（候选 < 5）；
        - low_confidence: 是否判定为低置信度（候选 < 3）；
        - rewrite_retry_count: 查询改写重试次数；
        - fallback_triggered: 最后触发的兜底动作（rewrite_retry / upscale / hyde）；
        - history_lookup: 是否启用了历史版本查询模式。

        返回值：
        RetrievalDebugTrace 对象，可直接赋值给 KnowledgeAnswerPayload.retrieval_debug。
        """
        return RetrievalDebugTrace(
            original_query=original_query,
            rewritten_query=rewritten_query,
            acl_filter=acl_filter,
            profile=profile,
            bias_mode=bias_mode,
            dense_candidates=dense_candidates or [],
            sparse_candidates=sparse_candidates or [],
            rrf_merged=rrf_merged or [],
            reranked_top=reranked_top or [],
            low_recall=low_recall,
            low_confidence=low_confidence,
            rewrite_retry_count=rewrite_retry_count,
            fallback_triggered=fallback_triggered,
            history_lookup=history_lookup,
        )
