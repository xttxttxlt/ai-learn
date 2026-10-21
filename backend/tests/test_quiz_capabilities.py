from decimal import Decimal

from fastapi.testclient import TestClient

import app.services.user_service as user_service
from app.core.auth import create_token
from app.core.config import Settings
from app.main import app
from tests.fake_db import USER_ROW, FakeDB

client = TestClient(app)
HEADERS = {"Authorization": f"Bearer {create_token(7, 'openid_test')}"}


def _settings(**overrides):
    values = {
        "_env_file": None,
        "tavily_api_key": "tvly-test",
        "enable_web_search": True,
        "dashscope_api_key": "dashscope-test",
        "enable_knowledge_base": True,
        "enable_image_generation": True,
        "cos_secret_id": "secret-id",
        "cos_secret_key": "secret-key",
        "cos_region": "ap-guangzhou",
        "cos_bucket": "bucket-1250000000",
        "image_daily_limit": 100,
    }
    values.update(overrides)
    return Settings(**values)


def _prepare_profile(fake, image_count=3):
    fake.fetch_one_queue = [
        dict(USER_ROW),
        {"quiz_count": 2, "correct_count": 8, "avg_accuracy": Decimal("80.00")},
        {"image_count": image_count},
    ]


def test_profile_reports_all_capabilities_ready(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    _prepare_profile(fake)
    monkeypatch.setattr(user_service, "get_settings", lambda: _settings())

    body = client.get("/api/v1/user/profile", headers=HEADERS).json()

    assert body["code"] == 0
    assert body["data"]["quiz_capabilities"] == {
        "web_search": True,
        "knowledge_base": True,
        "image_generation": True,
    }
    assert body["data"]["image_quota"]["available"] is True


def test_profile_reports_unavailable_capabilities(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    _prepare_profile(fake)
    monkeypatch.setattr(
        user_service,
        "get_settings",
        lambda: _settings(
            tavily_api_key="",
            enable_web_search=False,
            dashscope_api_key="",
            enable_knowledge_base=True,
            enable_image_generation=True,
            cos_bucket="",
        ),
    )

    body = client.get("/api/v1/user/profile", headers=HEADERS).json()

    assert body["data"]["quiz_capabilities"] == {
        "web_search": False,
        "knowledge_base": False,
        "image_generation": False,
    }
    assert body["data"]["image_quota"]["available"] is False


def test_profile_image_quota_unavailable_when_generation_disabled(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    _prepare_profile(fake, image_count=0)
    monkeypatch.setattr(
        user_service,
        "get_settings",
        lambda: _settings(enable_image_generation=False),
    )

    body = client.get("/api/v1/user/profile", headers=HEADERS).json()

    assert body["data"]["quiz_capabilities"]["image_generation"] is False
    assert body["data"]["image_quota"]["available"] is False
    assert body["data"]["image_quota"]["remaining"] == 100
