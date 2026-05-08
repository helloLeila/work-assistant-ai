"""检索结果评估链。"""

from __future__ import annotations

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.core.config import get_settings
from app.core.llm import get_chat_model
from app.models.domain import GradeResult


async def grade_retrieval(query: str, documents: list[dict[str, object]]) -> GradeResult:
    """判断检索结果是否足以回答问题。"""
    if not documents:
        return GradeResult(relevant=False, score=0.0, reason="未检索到文档")

    llm = get_chat_model(temperature=0, tags=["retrieval_grader"])
    parser = PydanticOutputParser(pydantic_object=GradeResult)
    top_documents = "\n\n".join(
        f"[{item['source_file']}#{item['page_num']}] {str(item['content'])[:320]}" for item in documents[:3]
    )

    if llm is not None:
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", "你负责评估检索结果是否足以回答用户问题，只输出 JSON。"),
                ("human", "格式：{format_instructions}\n\n问题：{query}\n\n检索结果：\n{documents}"),
            ]
        )
        chain = prompt | llm | parser
        return await chain.ainvoke(
            {
                "format_instructions": parser.get_format_instructions(),
                "query": query,
                "documents": top_documents,
            }
        )

    top_score = float(documents[0]["score"])
    return GradeResult(
        relevant=top_score >= get_settings().llm_relevance_threshold / 2,
        score=top_score,
        reason="根据本地检索分数进行启发式判断",
    )
