from fastapi.testclient import TestClient

import app.services.user_service as user_service
from app.core.auth import create_token
from app.core.exceptions import WechatLoginError
from app.main import app
from tests.fake_db import USER_ROW, FakeDB

client = TestClient(app)


def _auth_header(user_id: int = 7) -> dict:
    return {"Authorization": f"Bearer {create_token(user_id, 'openid_test')}"}


async def _fake_code2session(code: str) -> str:
    return "openid_test"


def test_login_new_user_registers(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    monkeypatch.setattr(user_service, "code2session", _fake_code2session)
    # get_by_openid -> None；create -> id=7；get_by_id -> row
    fake.fetch_one_queue = [None, dict(USER_ROW)]
    fake.execute_queue = [(7, 1)]

    resp = client.post("/api/v1/user/login", json={"code": "wx_code"})
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["token"]
    assert body["data"]["user"]["id"] == 7
    assert body["data"]["user"]["nickname"] == "学习者"
    # 验证 token 可解析出 user_id
    from app.core.auth import decode_token

    payload = decode_token(body["data"]["token"])
    assert payload["user_id"] == 7
    assert payload["openid"] == "openid_test"


def test_login_existing_user(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    monkeypatch.setattr(user_service, "code2session", _fake_code2session)
    fake.fetch_one_queue = [dict(USER_ROW)]

    resp = client.post("/api/v1/user/login", json={"code": "wx_code"})
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["user"]["total_coins"] == 30
    assert fake.executed == []  # 老用户不再 INSERT


def test_login_wechat_error_returns_4004(monkeypatch):
    FakeDB().install(monkeypatch)

    async def boom(code: str) -> str:
        raise WechatLoginError()

    monkeypatch.setattr(user_service, "code2session", boom)
    resp = client.post("/api/v1/user/login", json={"code": "bad"})
    assert resp.json()["code"] == 4004


def test_login_empty_code_returns_4000():
    resp = client.post("/api/v1/user/login", json={"code": ""})
    assert resp.json()["code"] == 4000


def test_profile_requires_auth():
    resp = client.get("/api/v1/user/profile")
    assert resp.json()["code"] == 4010
    resp = client.get("/api/v1/user/profile", headers={"Authorization": "Bearer bad"})
    assert resp.json()["code"] == 4010


def test_get_profile_success(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    from decimal import Decimal

    fake.fetch_one_queue = [
        dict(USER_ROW),
        {"quiz_count": 2, "correct_count": 8, "avg_accuracy": Decimal("80.00")},
    ]
    resp = client.get("/api/v1/user/profile", headers=_auth_header())
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["id"] == 7
    assert data["total_coins"] == 30
    assert data["quiz_count"] == 2
    assert data["correct_count"] == 8
    assert data["average_accuracy"] == 80


def test_update_profile(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    updated = dict(USER_ROW, nickname="小皮同学")
    fake.fetch_one_queue = [
        dict(USER_ROW),  # update_profile 前置校验
        updated,  # get_profile 读用户
        {"quiz_count": 0, "correct_count": 0, "avg_accuracy": 0},
    ]
    resp = client.put(
        "/api/v1/user/profile", json={"nickname": "小皮同学"}, headers=_auth_header()
    )
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["nickname"] == "小皮同学"
    assert any("UPDATE users SET" in sql for sql, _ in fake.executed)


def test_update_profile_empty_body_is_noop(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.fetch_one_queue = [
        dict(USER_ROW),
        dict(USER_ROW),
        {"quiz_count": 0, "correct_count": 0, "avg_accuracy": 0},
    ]
    resp = client.put("/api/v1/user/profile", json={}, headers=_auth_header())
    assert resp.json()["code"] == 0
    assert fake.executed == []


def test_quizzes_requires_auth():
    resp = client.get("/api/v1/user/quizzes")
    assert resp.json()["code"] == 4010
