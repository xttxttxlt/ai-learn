import pytest

from app.core.config import Settings

_IMAGE_ENV_KEYS = (
    "ENABLE_IMAGE_GENERATION",
    "IMAGE_BASE_URL",
    "IMAGE_MODEL",
    "IMAGE_SIZE",
    "IMAGE_TIMEOUT_SECONDS",
    "IMAGE_MAX_CONCURRENCY",
    "IMAGE_DAILY_LIMIT",
    "COS_SECRET_ID",
    "COS_SECRET_KEY",
    "COS_REGION",
    "COS_BUCKET",
    "COS_PUBLIC_BASE_URL",
    "COS_KEY_PREFIX",
    "DASHSCOPE_API_KEY",
)


@pytest.fixture(autouse=True)
def _clean_image_env(monkeypatch):
    for key in _IMAGE_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_image_generation_defaults():
    settings = Settings(_env_file=None)

    assert settings.enable_image_generation is True
    assert settings.image_base_url == "https://dashscope.aliyuncs.com/api/v1"
    assert settings.image_model == "qwen-image-3.0"
    assert settings.image_size == "512*512"
    assert settings.image_timeout_seconds == 45
    assert settings.image_max_concurrency == 6
    assert settings.image_daily_limit == 100
    assert settings.image_max_retries == 3
    assert settings.image_retry_backoff_seconds == 2.0
    assert settings.cos_secret_id == ""
    assert settings.cos_secret_key == ""
    assert settings.cos_region == ""
    assert settings.cos_bucket == ""
    assert settings.cos_public_base_url == ""
    assert settings.cos_key_prefix == "question-images"


def test_image_generation_ready_requires_all_credentials():
    ready = Settings(
        _env_file=None,
        dashscope_api_key="ds-key",
        cos_secret_id="id",
        cos_secret_key="key",
        cos_region="ap-guangzhou",
        cos_bucket="bucket-1250000000",
    )
    assert ready.image_generation_ready is True


@pytest.mark.parametrize(
    "overrides",
    [
        {"dashscope_api_key": ""},
        {"cos_secret_id": ""},
        {"cos_secret_key": ""},
        {"cos_region": ""},
        {"cos_bucket": ""},
        {"enable_image_generation": False},
    ],
)
def test_image_generation_ready_false_when_any_requirement_missing(overrides):
    values = {
        "dashscope_api_key": "ds-key",
        "cos_secret_id": "id",
        "cos_secret_key": "key",
        "cos_region": "ap-guangzhou",
        "cos_bucket": "bucket-1250000000",
    }
    values.update(overrides)

    assert Settings(_env_file=None, **values).image_generation_ready is False
