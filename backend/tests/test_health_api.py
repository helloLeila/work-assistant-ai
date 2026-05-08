"""后端健康检查测试。

这个测试先定义我们希望看到的外部行为，
然后再去写真正的 FastAPI 代码。
"""

from fastapi.testclient import TestClient

from app.main import create_app


def test_health_endpoint_returns_project_metadata() -> None:
    """健康检查接口应该返回项目名和当前版本。"""
    client = TestClient(create_app())

    response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["project"] == "企业智能办公助手"
    assert payload["version"] == "1.0.0"
