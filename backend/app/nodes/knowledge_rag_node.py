"""知识检索节点。"""

from __future__ import annotations

from app.chains.rag_chain import run_rag_chain


async def knowledge_rag_node(state: dict) -> dict:
    """执行知识库检索。"""
    result = await run_rag_chain(state["query"])
    return {
        "retrieved_docs": result["documents"],
        "draft_answer": result["answer"],
        "sources": result["sources"],
    }
