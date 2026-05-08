"""聊天流接口测试。"""

from fastapi.testclient import TestClient

from app.main import create_app


def test_chat_stream_returns_sse_events() -> None:
    """聊天流接口应返回符合 SSE 格式的事件。"""
    client = TestClient(create_app())

    login_response = client.post(
        "/api/auth/login",
        json={"username": "li.wei", "password": "TongTong123!"},
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
        json={"username": "li.wei", "password": "TongTong123!"},
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
