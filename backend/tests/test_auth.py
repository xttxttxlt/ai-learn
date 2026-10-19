import time

import jwt as pyjwt
import pytest
from fastapi import Request

from app.core.auth import (
    AuthUser,
    create_token,
    decode_token,
    get_current_user,
    get_optional_user,
)
from app.core.config import get_settings
from app.core.exceptions import UnauthorizedError


def _request(auth_header: str | None = None) -> Request:
    headers = {"authorization": auth_header} if auth_header else {}
    scope = {"type": "http", "method": "GET", "path": "/", "headers": [
        (k.lower().encode(), v.encode()) for k, v in headers.items()
    ]}
    return Request(scope)


def test_create_decode_roundtrip():
    token = create_token(42, "openid_abc")
    payload = decode_token(token)
    assert payload is not None
    assert payload["user_id"] == 42
    assert payload["openid"] == "openid_abc"
    assert payload["exp"] > time.time()


def test_decode_tampered_token_returns_none():
    token = create_token(1, "o")
    bad = pyjwt.encode({"user_id": 1}, "wrong-secret", algorithm="HS256")
    assert decode_token(token + "x") is None
    assert decode_token(bad) is None
    assert decode_token("not-a-jwt") is None


def test_decode_expired_token_returns_none():
    settings = get_settings()
    payload = {"user_id": 1, "openid": "o", "exp": int(time.time()) - 10}
    token = pyjwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    assert decode_token(token) is None


async def test_get_current_user_ok():
    token = create_token(7, "openid_x")
    user = await get_current_user(_request(f"Bearer {token}"))
    assert isinstance(user, AuthUser)
    assert user.user_id == 7
    assert user.openid == "openid_x"


async def test_get_current_user_missing_or_invalid_raises_4010():
    with pytest.raises(UnauthorizedError):
        await get_current_user(_request(None))
    with pytest.raises(UnauthorizedError):
        await get_current_user(_request("Bearer garbage"))
    with pytest.raises(UnauthorizedError):
        await get_current_user(_request("Basic abc"))


async def test_get_optional_user_returns_none_when_absent():
    assert await get_optional_user(_request(None)) is None
    assert await get_optional_user(_request("Bearer garbage")) is None
    token = create_token(3, "o3")
    user = await get_optional_user(_request(f"Bearer {token}"))
    assert user is not None and user.user_id == 3
