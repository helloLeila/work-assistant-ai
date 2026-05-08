"""外部补充检索节点。"""

from __future__ import annotations


async def web_search_node(state: dict) -> dict:
    """当前版本用站内补充说明代替外部搜索。"""
    query = state["query"]
    supplemental_text = f"当前知识库中没有足够材料直接回答“{query}”，建议补充相关制度或流程文档。"
    return {
        "structured_data": {"web_fallback": supplemental_text},
        "sources": state.get("sources", []),
    }
