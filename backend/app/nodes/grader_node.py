"""检索评估节点。"""

from __future__ import annotations

from app.chains.grading_chain import grade_retrieval


async def grader_node(state: dict) -> dict:
    """判断检索结果是否足够。"""
    documents = [
        {
            "source_file": item["source_file"],
            "page_num": item["page_num"],
            "content": item["snippet"],
            "score": item["score"],
        }
        for item in state.get("sources", [])
    ]
    result = await grade_retrieval(state["query"], documents)
    return {
        "relevant": result.relevant,
        "retrieval_score": result.score,
        "retrieval_reason": result.reason,
    }


def route_after_grade(state: dict) -> str:
    """根据评估结果决定是否走外部补充。"""
    return "generate_node" if state.get("relevant") else "web_search_node"
