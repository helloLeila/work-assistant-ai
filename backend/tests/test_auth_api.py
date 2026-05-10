"""认证接口测试。"""

from fastapi.testclient import TestClient

from app.main import create_app


def test_login_and_refresh_flow() -> None:
    """登录接口应返回双 Token，刷新接口应能换发新的访问令牌。"""
    client = TestClient(create_app())

    login_response = client.post(
        "/api/auth/login",
        json={"username": "li.wei", "password": "RuiRui123!"},
    )

    assert login_response.status_code == 200
    login_payload = login_response.json()
    assert login_payload["access_token"]
    assert login_payload["refresh_token"]
    assert login_payload["user"]["role"] == "employee"

    refresh_response = client.post(
        "/api/auth/refresh",
        json={"refresh_token": login_payload["refresh_token"]},
    )

    assert refresh_response.status_code == 200
    refresh_payload = refresh_response.json()
    assert refresh_payload["access_token"]
    assert refresh_payload["refresh_token"]
