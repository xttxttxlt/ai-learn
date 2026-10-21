from decimal import Decimal

from fastapi.testclient import TestClient

import app.services.user_service as user_service
from app.core.auth import create_token
from app.core.config import Settings
from app.core.exceptions import WechatLoginError
from app.main import app
from app.services import avatar_service
from tests.fake_db import USER_ROW, FakeDB

client = TestClient(app)


def _avatar_settings(**overrides):
    values = {
        "_env_file": None,
        "cos_secret_id": "secret-id",
        "cos_secret_key": "secret-key",
        "cos_region": "ap-guangzhou",
        "cos_bucket": "bucket-1250000000",
        "cos_avatar_prefix": "avatars",
        "avatar_max_file_mb": 2,
    }
    values.update(overrides)
    return Settings(**values)


JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 32


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


def test_get_profile_includes_beijing_image_quota(monkeypatch):
    from datetime import date

    fake = FakeDB().install(monkeypatch)
    fake.fetch_one_queue = [
        dict(USER_ROW),
        {"quiz_count": 2, "correct_count": 8, "avg_accuracy": Decimal("80.00")},
        {"image_count": 35},
    ]
    monkeypatch.setattr(
        user_service, "get_settings", lambda: Settings(_env_file=None, image_daily_limit=100)
    )
    monkeypatch.setattr(user_service, "beijing_today", lambda: date(2026, 10, 21))

    resp = client.get("/api/v1/user/profile", headers=_auth_header())

    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["image_quota"] == {
        "usage_date": "2026-10-21",
        "used": 35,
        "limit": 100,
        "remaining": 65,
        "available": True,
    }
    assert fake.fetch_one_calls[-1][1] == (7, date(2026, 10, 21))


def test_get_profile_quota_failure_does_not_fail_profile(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.fetch_one_queue = [
        dict(USER_ROW),
        {"quiz_count": 0, "correct_count": 0, "avg_accuracy": 0},
    ]
    monkeypatch.setattr(
        user_service, "get_settings", lambda: Settings(_env_file=None, image_daily_limit=100)
    )

    async def boom(user_id, usage_date):
        raise RuntimeError("db down")

    monkeypatch.setattr(
        user_service.image_usage_repository, "get_count", boom
    )

    resp = client.get("/api/v1/user/profile", headers=_auth_header())

    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["nickname"] == "学习者"
    assert body["data"]["image_quota"] == {
        "usage_date": body["data"]["image_quota"]["usage_date"],
        "used": 0,
        "limit": 100,
        "remaining": 100,
        "available": False,
    }


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


def test_avatar_requires_auth():
    resp = client.post(
        "/api/v1/user/avatar", files={"file": ("avatar.jpg", JPEG_BYTES, "image/jpeg")}
    )

    assert resp.status_code == 200
    assert resp.json()["code"] == 4010


def test_avatar_upload_success_returns_profile(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    avatar_url = "https://cdn.example.com/avatars/7/a.jpg"
    fake.fetch_one_queue = [
        dict(USER_ROW, avatar_url=avatar_url),
        {"quiz_count": 0, "correct_count": 0, "avg_accuracy": 0},
    ]
    monkeypatch.setattr(
        avatar_service, "get_settings", lambda: _avatar_settings()
    )
    monkeypatch.setattr(
        avatar_service.cos_storage_service,
        "upload_bytes",
        lambda *args: avatar_url,
    )

    resp = client.post(
        "/api/v1/user/avatar",
        files={"file": ("avatar.jpg", JPEG_BYTES, "image/jpeg")},
        headers=_auth_header(),
    )

    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["avatar_url"] == avatar_url
    assert any(
        sql.startswith("UPDATE users SET avatar_url")
        for sql, _ in fake.executed
    )


def test_avatar_upload_rejects_unsupported_format(monkeypatch):
    FakeDB().install(monkeypatch)
    monkeypatch.setattr(
        avatar_service, "get_settings", lambda: _avatar_settings()
    )
    called = []
    monkeypatch.setattr(
        avatar_service.cos_storage_service,
        "upload_bytes",
        lambda *args: called.append(args) or "https://cdn.example.com/a.jpg",
    )

    resp = client.post(
        "/api/v1/user/avatar",
        files={"file": ("avatar.gif", b"GIF89a" + b"\x00" * 16, "image/gif")},
        headers=_auth_header(),
    )

    assert resp.json()["code"] == 4000
    assert called == []


def test_avatar_upload_returns_5001_when_cos_not_configured(monkeypatch):
    FakeDB().install(monkeypatch)
    monkeypatch.setattr(
        avatar_service,
        "get_settings",
        lambda: _avatar_settings(cos_bucket=""),
    )

    resp = client.post(
        "/api/v1/user/avatar",
        files={"file": ("avatar.jpg", JPEG_BYTES, "image/jpeg")},
        headers=_auth_header(),
    )

    assert resp.json()["code"] == 5001
