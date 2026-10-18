from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_unified_ok():
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["message"] == "ok"
    assert body["data"]["status"] == "healthy"
