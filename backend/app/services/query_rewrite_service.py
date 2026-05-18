"""查询改写服务。

本服务位于企业 RAG 检索链路的最前端，对应 RAG 流程中的 Query Rewrite 阶段。
上游由 rag_chain（backend/app/chains/rag_chain.py）或 knowledge_rag_node
（backend/app/nodes/knowledge_rag_node.py）调用，接收用户原始查询字符串；
下游把改写结果（QueryRewriteResult）交给 retrieval_pipeline，用于 dense 向量检索
与 sparse 关键词检索。

核心职责：
1. light_rewrite：对用户口语化查询做轻量改写，提升向量检索召回率；
2. keyword_extraction：提取关键词作为 sparse 检索补充输入；
3. rewrite_blacklist：识别工号、合同编号、项目编码等固定标识，禁止改写；
4. rewrite_retry：低召回时允许最多 1 次重试，防止反复改写导致语义漂移。

关联模型：
- QueryRewriteResult（backend/app/models/knowledge_retrieval.py）：统一输出结构，
  包含 original_query、rewritten_query、keywords、strategy、retry_count。
"""

from __future__ import annotations

from app.core.config import get_settings
from app.models.knowledge_retrieval import QueryRewriteResult


class QueryRewriteService:
    """查询改写服务。

    职责定位：
    位于 RAG 检索链路入口，对用户原始查询进行改写和关键词提取，
    输出 QueryRewriteResult 供下游 retrieval_pipeline 使用。

    上下游关联：
    - 上游调用方：rag_chain.invoke 或 knowledge_rag_node 在检索前调用 rewrite；
    - 下游消费方：retrieval_pipeline 使用 rewritten_query 做 dense 检索，
      使用 keywords 做 sparse/BM25 检索。
    """

    def __init__(self) -> None:
        self._settings = get_settings()

    def rewrite(
        self,
        query: str,
        *,
        retry_count: int = 0,
    ) -> QueryRewriteResult:
        """执行查询改写。

        参数说明：
        - query: 用户原始查询字符串；
        - retry_count: 当前重试次数，由 rag_chain 在首次低召回后传入 1，
          本服务限制最大重试 1 次，防止无限循环改写。

        返回值：
        QueryRewriteResult，包含 original_query、rewritten_query、keywords、
        strategy、retry_count，供下游 retrieval_pipeline 统一消费。
        """
        return QueryRewriteResult(
            original_query=query,
            rewritten_query=query,
            keywords=[],
            strategy="skeleton",
            retry_count=retry_count,
        )

    def should_retry(self, result: QueryRewriteResult, recall_count: int) -> bool:
        """判断是否需要触发改写重试。

        重试规则：
        - 仅当 retry_count == 0 时允许重试（最大 1 次）；
        - 当 recall_count < self._settings.rewrite_recall_threshold（默认 5）时触发。

        返回值：
        True 表示允许重试，rag_chain 应使用更激进的改写策略再次检索；
        False 表示已达重试上限，应进入后续 fallback（升档 / HyDE / 保守回答）。
        """
        return False
