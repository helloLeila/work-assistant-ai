"""聊天流接口测试。"""

import json

from fastapi.testclient import TestClient

from app.main import create_app
from app.models.domain import WebSearchHit, WebSearchResult


def _extract_token_text(body: str) -> str:
    parts: list[str] = []
    for line in body.splitlines():
        if not line.startswith("data: "):
            continue
        payload = json.loads(line.removeprefix("data: "))
        if payload.get("type") == "token":
            parts.append(payload.get("content", ""))
    return "".join(parts)


def test_chat_stream_returns_sse_events() -> None:
    """聊天流接口应返回符合 SSE 格式的事件。"""
    client = TestClient(create_app())

    login_response = client.post(
        "/api/auth/login",
        json={"username": "li.wei", "password": "RuiRui123!"},
    )
    token = login_response.json()["access_token"]

    with client.stream(
        "POST",
        "/api/chat/stream",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "session_id": "session-test-001",
            "query": "请查询我这个月的薪酬总包",
        },
    ) as response:
        body = "".join(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk for chunk in response.iter_text())

    assert response.status_code == 200
    assert 'data: {"type":"token"' in body
    assert 'data: {"type":"done"}' in body


def test_chat_stream_get_supports_event_source_token_query() -> None:
    """GET 版 SSE 应支持 EventSource 通过查询参数传令牌。"""
    client = TestClient(create_app())

    login_response = client.post(
        "/api/auth/login",
        json={"username": "li.wei", "password": "RuiRui123!"},
    )
    token = login_response.json()["access_token"]

    with client.stream(
        "GET",
        "/api/chat/stream",
        params={
            "session_id": "session-test-002",
            "query": "帮我查看我的剩余年假",
            "access_token": token,
        },
    ) as response:
        body = "".join(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk for chunk in response.iter_text())

    assert response.status_code == 200
    assert 'data: {"type":"token"' in body
    assert 'data: {"type":"done"}' in body


def test_chat_stream_greeting_uses_planner_path_without_error() -> None:
    """问候语走 chitchat/planner 路径时不应抛图路由错误。"""
    client = TestClient(create_app())

    login_response = client.post(
        "/api/auth/login",
        json={"username": "li.wei", "password": "RuiRui123!"},
    )
    token = login_response.json()["access_token"]

    with client.stream(
        "GET",
        "/api/chat/stream",
        params={
            "session_id": "session-test-hello",
            "query": "你好",
            "access_token": token,
        },
    ) as response:
        body = "".join(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk for chunk in response.iter_text())

    assert response.status_code == 200
    assert 'data: {"type":"error"' not in body
    assert "企业智能办公助手" in _extract_token_text(body)
    assert 'data: {"type":"done"}' in body


def test_chat_stream_weather_query_uses_ip_augmented_search_and_skips_llm(monkeypatch) -> None:
    """天气类请求应透传客户端 IP，增强搜索词，并可在无主模型时直接回答。"""
    import app.nodes.generate_node as generate_module
    import app.nodes.web_search_node as web_search_module

    class FakeIPLocationService:
        async def lookup(self, ip: str) -> str | None:
            assert ip == "8.8.8.8"
            return "深圳"

    captured: dict[str, str] = {}

    class FakeWebSearchService:
        async def search(self, query: str, *, max_results: int | None = None) -> WebSearchResult:
            captured["query"] = query
            return WebSearchResult(
                query=query,
                results=[
                    WebSearchHit(
                        title="深圳天气预报",
                        url="https://weather.example.com/shenzhen",
                        snippet="今天 26-31°C，多云，南风 3 级，降雨概率 20%。",
                        site_name="天气网",
                    )
                ],
            )

    async def fail_if_llm_is_used(**kwargs):
        raise AssertionError("weather direct answer should not call stream_final_answer")

    monkeypatch.setenv("BOCHA_API_KEY", "dummy-key")
    monkeypatch.setattr(web_search_module, "get_ip_location_service", lambda: FakeIPLocationService())
    monkeypatch.setattr(web_search_module, "get_web_search_service", lambda: FakeWebSearchService())
    monkeypatch.setattr(generate_module, "stream_final_answer", fail_if_llm_is_used)

    client = TestClient(create_app())
    login_response = client.post(
        "/api/auth/login",
        json={"username": "li.wei", "password": "RuiRui123!"},
    )
    token = login_response.json()["access_token"]

    with client.stream(
        "GET",
        "/api/chat/stream",
        headers={"X-Forwarded-For": "8.8.8.8"},
        params={
            "session_id": "session-test-weather",
            "query": "天气",
            "access_token": token,
        },
    ) as response:
        body = "".join(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk for chunk in response.iter_text())

    assert response.status_code == 200
    assert captured["query"] == "深圳 天气"
    assert 'data: {"type":"error"' not in body
    assert "深圳" in _extract_token_text(body)
    assert "多云" in _extract_token_text(body)
    assert 'data: {"type":"done"}' in body
