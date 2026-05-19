"""知识检索节点。

本节点位于 LangGraph 工作流的知识检索环节，对应 RAG 流程中的
"Rewrite → ACL → Hybrid Retrieval → RRF → Rerank → Grounded Answer" 阶段。
上游接收 state["query"] 与可选的 state["user"]，下游把检索结果写入 state，
供 grader_node 评估与 generate_node 生成带引用的回答。

兼容说明：
本节点已接入新的 run_retrieval_pipeline 链路，返回 KnowledgeAnswerPayload 中的
 citations 与 retrieval_debug；同时保留 draft_answer / sources / retrieved_docs
旧格式字段，保证 grader_node 与 generate_node 等下游节点在过渡期间正常工作。
"""

from __future__ import annotations

from langchain_core.documents import Document

from app.chains.rag_chain import run_retrieval_pipeline
from app.core.security import CurrentUser


async def knowledge_rag_node(state: dict) -> dict:
    """执行知识库检索（适配新 RAG 链路）。

    本节点调用 run_retrieval_pipeline 执行完整的检索链路，然后把返回的
    KnowledgeAnswerPayload 映射为 LangGraph state 中的多个字段。

    参数：
    - state: LangGraph 工作流状态字典，必须包含 "query" 键，可选包含 "user" 键。
      state["user"] 应为 CurrentUser 类型，用于 ACL 解析；缺失时使用开放策略。

    返回值：
    包含以下键的字典：
    - draft_answer: 检索生成的回答文本（旧格式，供 generate_node 使用）；
    - sources: 旧格式来源列表（供 grader_node 与 generate_node 兼容使用）；
    - retrieved_docs: Document 列表（旧格式，供 generate_node 兼容使用）；
    - citations: CitationItem 列表（新格式，供后续升级节点使用）；
    - retrieval_debug: RetrievalDebugTrace（新格式，供调试与排障使用）。
    """
    query = state["query"]
    user = state.get("user")
    if user is not None and not isinstance(user, CurrentUser):
        # 若 state 中的 user 不是预期类型，降级为 None（开放策略）
        user = None

    payload = await run_retrieval_pipeline(query, user=user)

    # 旧格式 sources（供 grader_node 与 generate_node 兼容使用）
    sources = [
        {
            "doc_id": c.doc_id,
            "source_file": c.source_file,
            "page_num": 1,
            "department": "",
            "score": 0.0,
            "snippet": c.snippet,
        }
        for c in payload.citations
    ]

    # 旧格式 retrieved_docs（Document 列表，供 generate_node 兼容使用）
    retrieved_docs = [
        Document(
            page_content=c.snippet,
            metadata={
                "doc_id": c.doc_id,
                "source_file": c.source_file,
                "page_num": 1,
                "department": "",
                "doc_type": "",
                "score": 0.0,
            },
        )
        for c in payload.citations
    ]

    return {
        "retrieved_docs": retrieved_docs,
        "draft_answer": payload.answer,
        "sources": sources,
        "citations": payload.citations,
        "retrieval_debug": payload.retrieval_debug,
    }
