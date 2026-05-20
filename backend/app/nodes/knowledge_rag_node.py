"""知识检索节点。

本节点位于 LangGraph 工作流的知识检索环节，对应 RAG 流程中的
"Rewrite → ACL → Hybrid Retrieval → RRF → Rerank → Grounded Answer" 阶段。
# 标准RAG问答执行流程
# 1. Query Rewrite：优化用户查询，规整语义
# 2. ACL（Access Control List ）：按用户权限过滤不可见知识库内容
# 3. Hybrid Retrieval：（稠密检索 Dense+稀疏检索 Sparse）检索双路召回
# 4. RRF（Reciprocal Rank Fusion ）：融合多路结果，去重统一排序
# 5. Rerank：结果重排序 / 精排
# 6. Grounded Answer：事实锚定式作答（基于检索到的真实知识库内容生成答案）

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
    KnowledgeAnswerPayload 映射为 LangGraph state 中的多个字段（给后面节点用的材料（答案、参考文档、来源、引用））。 兼容新旧数据格式，为下游节点提供统一的状态数据输出。

    Args:
        state: 工作流状态字典，必传 query，可选传当前用户信息用于权限校验
        传入：用户搜索问题 + 登录用户身份权限（部门、角色、查看范围）
    执行：根据用户权限筛掉看不到的文档，再执行整套检索逻辑
    Returns:
        包含检索文档、草稿答案、引用来源、调试信息的状态字典
        即合规可查看的知识库文本片段，依托资料生成的回答内容，回答对应的原文资料出处，检索全流程日志（排查报错使用）
    参数：
    - state: LangGraph 工作流状态字典，必须包含 "query" 键，可选包含 "user" 键。
      state["user"] 应为 CurrentUser 类型，用于 ACL 解析；缺失时使用开放策略。
    
    """

    # 1. 提取查询语句与当前用户（用于ACL权限过滤）
    query = state["query"]
    user = state.get("user")

    # 2.  校验用户身份格式，非法则降级为公开访问策略
    if user is not None and not isinstance(user, CurrentUser):
        # 若 state 中的 user 不是预期类型，降级为 None（开放策略）
        user = None
    # 3. 执行标准RAG检索流水线，获取包含答案、引用与调试信息的完整载荷
    payload = await run_retrieval_pipeline(query, user=user)

    #  4. 构造旧版兼容格式：来源列表（供 grader_node 与 generate_node 兼容使用）
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

    #  5. 构造旧版兼容格式：LangChain Document 列表（供 generate_node 兼容使用）
    retrieved_docs = [
        Document(
            # 旧格式 content 字段使用 snippet，保持与之前一致；
            # 新链路中 content 可能包含更完整文本，后续可考虑调整 generate_node 以利用更丰富的内容
            page_content=c.snippet, 
            metadata={
                "doc_id": c.doc_id,
                "source_file": c.source_file,
                "page_num": 1,
                "department": "",
                "doc_type": "",
                "score": 0.0, # 新链路中 score 可能由 RRF 或 rerank 提供，旧链路中默认为 0.0
            },
        )
        for c in payload.citations # 这里直接使用 citations 构建 retrieved_docs，保持与旧链路一致；后续可根据需要调整为使用 payload 中的其他字段
    ]
   # 6. 输出状态：给后面节点用的材料（答案、参考文档、来源、引用），新老格式并存，保证系统平滑兼容与升级
    """返回值：
    包含以下键的字典：
    - draft_answer: 检索生成的回答文本（旧格式，供 generate_node 使用）；
    - sources: 旧格式来源列表（供 grader_node 与 generate_node 兼容使用）；
    - retrieved_docs: Document 列表（旧格式，供 generate_node 兼容使用）；
    - citations: CitationItem 列表（新格式，供后续升级节点使用）；
    - retrieval_debug: RetrievalDebugTrace（新格式，供调试与排障使用）。
    """
    return {
        "retrieved_docs": retrieved_docs,#合规可查看的知识库文本片段
        "draft_answer": payload.answer,#依托资料生成的回答内容
        "sources": sources,#回答对应的原文资料出处
        "citations": payload.citations,# 新格式资料引用列表（带文档ID/章节信息，用于前端溯源）
        "retrieval_debug": payload.retrieval_debug,#检索全流程日志（排查报错使用）
    }
