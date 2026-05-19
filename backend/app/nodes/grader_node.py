"""检索评估节点。

本节点位于 LangGraph 工作流的评估环节，对应 RAG 流程中的 Grading 阶段。
上游接收 knowledge_rag_node 的检索结果（sources 或 citations）；
下游根据评估分数决定路由到 generate_node（结果足够）或 web_search_node（需要补充）。

兼容说明：
本节点已适配新的 CitationItem 格式，优先从 state["citations"] 构建评估输入；
当 citations 缺失时（旧链路或未命中文档），回退到 state["sources"]，
保证与旧格式 state 的向后兼容。
"""

from __future__ import annotations

from app.chains.grading_chain import grade_retrieval
from app.models.knowledge_retrieval import CitationItem


async def grader_node(state: dict) -> dict:
    """判断检索结果是否足够。

    本节点从 state 中提取检索来源，构建 grading_chain 所需的 documents 列表，
    然后调用 grade_retrieval 进行评估。

    参数：
    - state: LangGraph 工作流状态字典，应包含 "query" 以及 "citations" 或 "sources"。

    返回值：
    包含以下键的字典：
    - relevant: bool，检索结果是否足够回答查询；
    - retrieval_score: float，检索质量评分；
    - retrieval_reason: str，评估原因说明。
    """
    # 优先从新格式 citations 读取，缺失时回退到旧格式 sources
    citations: list[CitationItem] = state.get("citations", [])
    sources: list[dict] = state.get("sources", [])

    if citations:
        documents = [
            {
                "source_file": c.source_file,
                "page_num": 1,
                "content": c.snippet,
                "score": 0.0,
            }
            for c in citations
        ]
    else:
        documents = [
            {
                "source_file": item.get("source_file", ""),
                "page_num": item.get("page_num", 1),
                "content": item.get("snippet", ""),
                "score": item.get("score", 0.0),
            }
            for item in sources
        ]

    result = await grade_retrieval(state["query"], documents)
    return {
        "relevant": result.relevant,
        "retrieval_score": result.score,
        "retrieval_reason": result.reason,
    }


def route_after_grade(state: dict) -> str:
    """根据评估结果决定是否走外部补充。

    参数：
    - state: LangGraph 工作流状态字典，应包含 "relevant" 键。

    返回值：
    "generate_node" 表示检索结果足够，进入生成节点；
    "web_search_node" 表示检索不足，进入联网搜索补充。
    """
    return "generate_node" if state.get("relevant") else "web_search_node"
