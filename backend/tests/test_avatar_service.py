import re
from datetime import datetime

import pytest

from app.core.config import Settings
from app.core.exceptions import ServiceUnavailableError, ValidationError
from app.services import cos_storage_service


def _settings(**overrides):
    values = {
        "_env_file": None,
        "cos_secret_id": "secret-id",
        "cos_secret_key": "secret-key",
        "cos_region": "ap-guangzhou",
        "cos_bucket": "bucket-1250000000",
        "cos_avatar_prefix": "avatars",
    }
    values.update(overrides)
    return Settings(**values)


def test_build_avatar_object_key_uses_user_date_and_random_name():
    key = cos_storage_service.build_avatar_object_key(
        7, "jpg", prefix="avatars", now=datetime(2026, 10, 21, 15, 30)
    )

    assert re.fullmatch(r"avatars/7/20261021/[0-9a-f]{32}\.jpg", key)


def test_build_avatar_object_key_uses_custom_prefix():
    key = cos_storage_service.build_avatar_object_key(
        7, "png", prefix="/custom/", now=datetime(2026, 10, 21, 15, 30)
    )

    assert key.startswith("custom/7/20261021/")
    assert key.endswith(".png")


def test_upload_bytes_sets_public_read_and_content_type(monkeypatch):
    calls: list[dict] = []

    class FakeClient:
        def put_object(self, **kwargs):
            calls.append(kwargs)
            return {"ETag": "etag"}

    monkeypatch.setattr(
        cos_storage_service, "_create_client", lambda settings: FakeClient()
    )

    url = cos_storage_service.upload_bytes(
        b"avatar-bytes", "avatars/7/a.jpg", _settings(), "image/jpeg"
    )

    assert url == (
        "https://bucket-1250000000.cos.ap-guangzhou.myqcloud.com/avatars/7/a.jpg"
    )
    assert calls[0]["Bucket"] == "bucket-1250000000"
    assert calls[0]["Body"] == b"avatar-bytes"
    assert calls[0]["Key"] == "avatars/7/a.jpg"
    assert calls[0]["ContentType"] == "image/jpeg"
    assert calls[0]["ACL"] == "public-read"


def test_upload_bytes_returns_empty_on_error(monkeypatch):
    class FakeClient:
        def put_object(self, **kwargs):
            raise RuntimeError("cos down")

    monkeypatch.setattr(
        cos_storage_service, "_create_client", lambda settings: FakeClient()
    )

    assert (
        cos_storage_service.upload_bytes(
            b"x", "avatars/7/a.jpg", _settings(), "image/jpeg"
        )
        == ""
    )


JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 32
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
WEBP_BYTES = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 32
GIF_BYTES = b"GIF89a" + b"\x00" * 32


class FakeUpload:
    def __init__(self, data: bytes):
        self.data = data
        self.read_sizes: list[int] = []

    async def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        return self.data if size < 0 else self.data[:size]


def _patch_success(monkeypatch, url="https://cdn.example.com/avatar.jpg"):
    from app.services import avatar_service

    calls: dict = {"uploaded": [], "updated": []}

    def fake_upload(data, key, settings, content_type):
        calls["uploaded"].append((data, key, content_type))
        return url

    async def fake_update(user_id, nickname=None, avatar_url=None):
        calls["updated"].append((user_id, nickname, avatar_url))

    monkeypatch.setattr(avatar_service.cos_storage_service, "upload_bytes", fake_upload)
    monkeypatch.setattr(
        avatar_service.user_repository, "update_profile", fake_update
    )
    return avatar_service, calls


@pytest.mark.parametrize(
    ("data", "expected_ext", "expected_content_type"),
    [
        (JPEG_BYTES, "jpg", "image/jpeg"),
        (PNG_BYTES, "png", "image/png"),
        (WEBP_BYTES, "webp", "image/webp"),
    ],
)
async def test_update_avatar_accepts_supported_image_types(
    monkeypatch, data, expected_ext, expected_content_type
):
    avatar_service, calls = _patch_success(monkeypatch)

    url = await avatar_service.update_avatar(
        7, FakeUpload(data), settings=_settings()
    )

    assert url == "https://cdn.example.com/avatar.jpg"
    uploaded_data, key, content_type = calls["uploaded"][0]
    assert uploaded_data == data
    assert key.startswith("avatars/7/") and key.endswith(f".{expected_ext}")
    assert content_type == expected_content_type
    assert calls["updated"] == [(7, None, url)]


async def test_update_avatar_rejects_empty_file(monkeypatch):
    avatar_service, calls = _patch_success(monkeypatch)

    with pytest.raises(ValidationError):
        await avatar_service.update_avatar(7, FakeUpload(b""), settings=_settings())

    assert calls["uploaded"] == []
    assert calls["updated"] == []


async def test_update_avatar_rejects_unsupported_format(monkeypatch):
    avatar_service, calls = _patch_success(monkeypatch)

    with pytest.raises(ValidationError):
        await avatar_service.update_avatar(
            7, FakeUpload(GIF_BYTES), settings=_settings()
        )

    assert calls["uploaded"] == []
    assert calls["updated"] == []


async def test_update_avatar_rejects_oversized_file(monkeypatch):
    avatar_service, calls = _patch_success(monkeypatch)
    settings = _settings(avatar_max_file_mb=1)
    oversized = JPEG_BYTES + b"0" * (1024 * 1024)

    with pytest.raises(ValidationError):
        await avatar_service.update_avatar(7, FakeUpload(oversized), settings=settings)

    assert calls["uploaded"] == []
    assert calls["updated"] == []


async def test_update_avatar_requires_cos_config(monkeypatch):
    from app.services import avatar_service

    called = []
    monkeypatch.setattr(
        avatar_service.cos_storage_service,
        "upload_bytes",
        lambda *args: called.append(args) or "https://cdn.example.com/a.jpg",
    )

    with pytest.raises(ServiceUnavailableError):
        await avatar_service.update_avatar(
            7, FakeUpload(JPEG_BYTES), settings=_settings(cos_bucket="")
        )

    assert called == []


async def test_update_avatar_keeps_old_avatar_when_cos_fails(monkeypatch):
    from app.services import avatar_service

    updated = []

    async def fake_update(*args, **kwargs):
        updated.append((args, kwargs))

    monkeypatch.setattr(
        avatar_service.cos_storage_service, "upload_bytes", lambda *args: ""
    )
    monkeypatch.setattr(avatar_service.user_repository, "update_profile", fake_update)

    with pytest.raises(ServiceUnavailableError):
        await avatar_service.update_avatar(
            7, FakeUpload(JPEG_BYTES), settings=_settings()
        )

    assert updated == []


async def test_update_avatar_returns_error_when_database_update_fails(monkeypatch):
    from app.services import avatar_service

    async def boom(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(
        avatar_service.cos_storage_service,
        "upload_bytes",
        lambda *args: "https://cdn.example.com/avatar.jpg",
    )
    monkeypatch.setattr(avatar_service.user_repository, "update_profile", boom)

    with pytest.raises(ServiceUnavailableError):
        await avatar_service.update_avatar(
            7, FakeUpload(JPEG_BYTES), settings=_settings()
        )
