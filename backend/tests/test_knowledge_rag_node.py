"""知识检索节点与路由测试。

本测试锁定 knowledge_rag_node、grader_node 与知识接口对新旧 payload 的兼容行为：
- knowledge_rag_node 必须返回 citations、retrieval_debug 等新字段；
- 同时保留 draft_answer、sources、retrieved_docs 供旧节点使用；
- grader_node 优先从 citations 构建评估输入，缺失时回退到 sources；
- 知识接口 /search 路由返回 KnowledgeAnswerPayload。

任何对节点 state 字段或路由响应格式的调整都必须在此验证。
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.models.knowledge_retrieval import CitationItem, KnowledgeAnswerPayload, RetrievalDebugTrace
from app.nodes.grader_node import grader_node
from app.nodes.knowledge_rag_node import knowledge_rag_node


class MockGradeResult:
    """GradeResult 的 mock，用于替代 grading_chain.grade_retrieval 返回值。"""

    def __init__(self, relevant: bool = True, score: float = 0.8, reason: str = "ok"):
        self.relevant = relevant
        self.score = score
        self.reason = reason


class TestKnowledgeRagNode:
    """测试知识检索节点适配新 payload。"""

    def test_returns_new_payload_fields(self) -> None:
        """knowledge_rag_node 必须返回 citations 与 retrieval_debug。"""
        state = {"query": "测试查询"}
        result = asyncio.run(knowledge_rag_node(state))
        assert "citations" in result
        assert "retrieval_debug" in result
        assert isinstance(result["citations"], list)
        assert isinstance(result["retrieval_debug"], RetrievalDebugTrace)

    def test_returns_legacy_fields(self) -> None:
        """knowledge_rag_node 必须保留 draft_answer / sources / retrieved_docs。"""
        state = {"query": "测试查询"}
        result = asyncio.run(knowledge_rag_node(state))
        assert "draft_answer" in result
        assert "sources" in result
        assert "retrieved_docs" in result
        assert isinstance(result["sources"], list)
        assert isinstance(result["retrieved_docs"], list)

    def test_citations_match_sources_length(self) -> None:
        """citations 与 sources 长度应一致（同源不同格式）。"""
        state = {"query": "测试查询"}
        result = asyncio.run(knowledge_rag_node(state))
        assert len(result["citations"]) == len(result["sources"])

    def test_citations_items_are_typed(self) -> None:
        """citations 列表中的元素应为 CitationItem 类型。"""
        state = {"query": "测试查询"}
        result = asyncio.run(knowledge_rag_node(state))
        for c in result["citations"]:
            assert isinstance(c, CitationItem)


class TestGraderNode:
    """测试评估节点对 citations 与 sources 的兼容读取。"""

    def test_reads_from_citations_when_available(self, monkeypatch) -> None:
        """state 中存在 citations 时，grader_node 应从 citations 构建 documents。"""
        captured: list[list[dict[str, Any]]] = []

        async def mock_grade(q: str, docs: list[dict[str, Any]]) -> MockGradeResult:
            captured.append(docs)
            return MockGradeResult()

        monkeypatch.setattr("app.nodes.grader_node.grade_retrieval", mock_grade)

        state = {
            "query": "测试",
            "citations": [
                CitationItem(doc_id="d1", source_file="a.txt", snippet="内容A"),
                CitationItem(doc_id="d2", source_file="b.txt", snippet="内容B"),
            ],
            "sources": [],  # 即使 sources 为空，也应优先读 citations
        }
        result = asyncio.run(grader_node(state))
        assert len(captured) == 1
        docs = captured[0]
        assert len(docs) == 2
        assert docs[0]["source_file"] == "a.txt"
        assert docs[0]["content"] == "内容A"
        assert "relevant" in result

    def test_fallback_to_sources_when_no_citations(self, monkeypatch) -> None:
        """state 中无 citations 时，grader_node 应回退到 sources 构建 documents。"""
        captured: list[list[dict[str, Any]]] = []

        async def mock_grade(q: str, docs: list[dict[str, Any]]) -> MockGradeResult:
            captured.append(docs)
            return MockGradeResult()

        monkeypatch.setattr("app.nodes.grader_node.grade_retrieval", mock_grade)

        state = {
            "query": "测试",
            "sources": [
                {
                    "source_file": "旧文件.txt",
                    "page_num": 3,
                    "snippet": "旧内容",
                    "score": 0.5,
                }
            ],
        }
        result = asyncio.run(grader_node(state))
        assert len(captured) == 1
        docs = captured[0]
        assert len(docs) == 1
        assert docs[0]["source_file"] == "旧文件.txt"
        assert docs[0]["page_num"] == 3
        assert docs[0]["content"] == "旧内容"
        assert docs[0]["score"] == 0.5
        assert "relevant" in result

    def test_empty_both_returns_grading_result(self, monkeypatch) -> None:
        """citations 与 sources 均为空时，grade_retrieval 应收到空列表。"""
        captured: list[list[dict[str, Any]]] = []

        async def mock_grade(q: str, docs: list[dict[str, Any]]) -> MockGradeResult:
            captured.append(docs)
            return MockGradeResult(relevant=False, score=0.0, reason="无文档")

        monkeypatch.setattr("app.nodes.grader_node.grade_retrieval", mock_grade)

        state = {"query": "测试"}
        result = asyncio.run(grader_node(state))
        assert len(captured) == 1
        assert captured[0] == []
        assert result["relevant"] is False
        assert result["retrieval_score"] == 0.0


class TestRouteAfterGrade:
    """测试评估后路由决策。"""

    def test_routes_to_generate_when_relevant(self) -> None:
        """relevant 为 True 时路由到 generate_node。"""
        from app.nodes.grader_node import route_after_grade

        assert route_after_grade({"relevant": True}) == "generate_node"

    def test_routes_to_web_search_when_not_relevant(self) -> None:
        """relevant 为 False 时路由到 web_search_node。"""
        from app.nodes.grader_node import route_after_grade

        assert route_after_grade({"relevant": False}) == "web_search_node"


class TestKnowledgeSearchRoute:
    """测试知识库检索路由 /search。"""

    def test_search_route_returns_payload(self) -> None:
        """/knowledge/search 应返回 KnowledgeAnswerPayload 类型。"""
        from fastapi.testclient import TestClient
        from app.api.deps import get_current_user
        from app.core.security import CurrentUser
        from app.main import app

        def mock_get_current_user() -> CurrentUser:
            return CurrentUser(
                user_id="test-user",
                username="test",
                name="Test User",
                role="employee",
                department="HR",
            )

        app.dependency_overrides[get_current_user] = mock_get_current_user
        try:
            client = TestClient(app)
            response = client.post("/api/knowledge/search", data={"query": "年假怎么休"})
            assert response.status_code == 200
            payload = response.json()
            assert "answer" in payload
            assert "citations" in payload
            assert "retrieval_debug" in payload
        finally:
            del app.dependency_overrides[get_current_user]
