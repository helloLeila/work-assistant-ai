"""重排服务。

本服务位于企业 RAG 检索链路的 RRF 融合阶段之后、Grounded Answer 生成之前。
上游由 KnowledgeVectorStore.search（backend/app/vectorstore/milvus_client.py）调用，
接收 RRF 融合后的候选列表；下游把精排后的 Top-K 结果交给 rag_chain 用于引用生成。

核心职责：
1. 对 RRF 融合后的候选做二次精排，把最相关的 chunk 排到前面；
2. 根据检索 profile 控制输入规模（默认 50 条，high_recall 最大 80 条），
   避免无限制候选拖慢响应；
3. 首版在没有 cross-encoder 时，基于候选已有的 dense score 做近似降序重排，
   保留统一接口，后续可无缝切换为 cross-encoder 或 Milvus native rerank。

关联模型：
- RetrievalDebugTrace（backend/app/models/knowledge_retrieval.py）：reranked_top 字段
  记录本服务输出，供调试追踪使用。
"""

from __future__ import annotations

from typing import Any

from app.core.config import get_settings


class RerankService:
    """重排服务。

    职责定位：
    位于 RAG 检索链路末端，对多路融合后的候选进行精排，
    输出少量高置信度 chunk 供下游生成阶段引用。

    上下游关联：
    - 上游调用方：KnowledgeVectorStore.search 在 RRF 融合后调用 rerank；
    - 下游消费方：rag_chain 使用 rerank 后的 Top-K 结果构建带引用的回答。
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._default_top_k: int = self._settings.knowledge_rerank_top_k
        self._input_max: int = self._settings.knowledge_rerank_input_max
        self._input_high_recall_max: int = self._settings.knowledge_rerank_input_high_recall_max

    def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        *,
        top_k: int | None = None,
        profile: str | None = None,
    ) -> list[dict[str, Any]]:
        """执行候选重排。

        参数说明：
        - query: 用户原始查询字符串，用于重排模型计算 query-chunk 相关性；
        - candidates: RRF 融合后的候选列表，每个元素至少包含 chunk_id、score、content；
        - top_k: 输出数量上限，None 时使用 config 中的 knowledge_rerank_top_k（默认 5）；
        - profile: 检索档位（faq_low_cost / standard / high_recall），控制输入候选上限。

        返回值：
        按相关性降序排列的候选列表，长度不超过 top_k。

        实现说明：
        首版基于候选已有的 score 字段做降序近似重排。后续引入 cross-encoder 时，
        只需替换内部排序逻辑，接口和调用方无需改动。
        """
        if not candidates:
            return []

        output_limit = top_k if top_k is not None else self._default_top_k
        input_limit = self._resolve_input_limit(profile)

        # 按输入上限截断候选，避免无限制规模拖慢响应
        trimmed = candidates[:input_limit]

        # 首版近似重排：基于已有 score 降序
        sorted_candidates = sorted(trimmed, key=lambda x: x.get("score", 0.0), reverse=True)

        return sorted_candidates[:output_limit]

    def _resolve_input_limit(self, profile: str | None) -> int:
        """根据检索档位解析 rerank 输入上限。

        参数：
        - profile: 检索档位，faq_low_cost / standard / high_recall。

        返回值：
        允许进入重排的最大候选数量。

        规则：
        - high_recall 允许最大 80 条（由 knowledge_rerank_input_high_recall_max 控制）；
        - 其他档位默认 50 条（由 knowledge_rerank_input_max 控制）。
        """
        if profile == "high_recall":
            return self._input_high_recall_max
        return self._input_max
