"""RAG 链与检索器。"""

from __future__ import annotations

from typing import Any

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.retrievers import BaseRetriever
from langchain_core.runnables import RunnablePassthrough
from pydantic import PrivateAttr

from app.core.llm import get_chat_model
from app.services.knowledge_service import get_knowledge_service


class KnowledgeRetriever(BaseRetriever):
    """封装知识库服务，供 LCEL 使用。"""

    department: str | None = None
    doc_type: str | None = None
    _service = PrivateAttr()

    def __init__(self, *, department: str | None = None, doc_type: str | None = None) -> None:
        super().__init__(department=department, doc_type=doc_type)
        self._service = get_knowledge_service()

    def _get_relevant_documents(self, query: str, *, run_manager=None) -> list[Document]:
        results = self._service.search(query, department=self.department, doc_type=self.doc_type)
        return [
            Document(
                page_content=str(item["content"]),
                metadata={
                    "doc_id": item["doc_id"],
                    "source_file": item["source_file"],
                    "page_num": item["page_num"],
                    "department": item["department"],
                    "doc_type": item["doc_type"],
                    "score": item["score"],
                },
            )
            for item in results
        ]

    async def _aget_relevant_documents(self, query: str, *, run_manager=None) -> list[Document]:
        return self._get_relevant_documents(query, run_manager=run_manager)


def format_documents(documents: list[Document]) -> str:
    """把文档格式化为可读上下文。"""
    return "\n\n".join(
        f"[{doc.metadata.get('source_file')} 第{doc.metadata.get('page_num')}段] {doc.page_content}" for doc in documents
    )


async def run_rag_chain(query: str, *, department: str | None = None, doc_type: str | None = None) -> dict[str, Any]:
    """执行 RAG 检索链。"""
    retriever = KnowledgeRetriever(department=department, doc_type=doc_type)
    documents = await retriever.ainvoke(query)

    llm = get_chat_model(temperature=0.1, tags=["rag_answer"])
    answer = ""
    if llm is not None and documents:
        prompt = ChatPromptTemplate.from_template(
            "你是企业知识库助手。请只依据给定上下文回答。\n\n问题：{question}\n\n上下文：\n{context}"
        )
        chain = {
            "context": retriever | format_documents,
            "question": RunnablePassthrough(),
        } | prompt | llm | StrOutputParser()
        answer = await chain.ainvoke(query)

    return {
        "answer": answer,
        "documents": documents,
        "sources": [
            {
                "doc_id": str(doc.metadata.get("doc_id")),
                "source_file": str(doc.metadata.get("source_file")),
                "page_num": int(doc.metadata.get("page_num", 1)),
                "department": str(doc.metadata.get("department", "")),
                "score": float(doc.metadata.get("score", 0.0)),
                "snippet": doc.page_content[:180],
            }
            for doc in documents
        ],
    }
