"""知识库接口测试。"""

from io import BytesIO

from fastapi.testclient import TestClient

from app.main import create_app


def test_upload_list_and_delete_document() -> None:
    """文档应支持上传、列表查询和删除。"""
    client = TestClient(create_app())

    login_response = client.post(
        "/api/auth/login",
        json={"username": "wang.hr", "password": "TongTong123!"},
    )
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    upload_response = client.post(
        "/api/knowledge/upload",
        headers=headers,
        files={"file": ("travel_policy.txt", BytesIO("差旅报销标准".encode("utf-8")), "text/plain")},
        data={"department": "Finance"},
    )

    assert upload_response.status_code == 200
    uploaded = upload_response.json()
    assert uploaded["doc_id"]

    list_response = client.get("/api/knowledge/list", headers=headers)
    assert list_response.status_code == 200
    assert any(item["doc_id"] == uploaded["doc_id"] for item in list_response.json()["items"])

    delete_response = client.delete(
        f"/api/knowledge/{uploaded['doc_id']}",
        headers=headers,
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True
