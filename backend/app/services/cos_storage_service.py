"""腾讯云 COS 图片上传：公有读桶、固定 URL。"""

import uuid
from datetime import date, datetime
from typing import Optional
from urllib.parse import quote

from app.core.config import Settings
from app.core.logging import get_logger
from app.utils.time_utils import beijing_now

logger = get_logger("cos_storage_service")


def _create_client(settings: Settings):
    from qcloud_cos import CosConfig, CosS3Client

    config = CosConfig(
        Region=settings.cos_region,
        SecretId=settings.cos_secret_id,
        SecretKey=settings.cos_secret_key,
        Scheme="https",
    )
    return CosS3Client(config)


def build_object_key(
    user_id: int,
    usage_date: date,
    quiz_id: str,
    question_index: int,
    prefix: str = "question-images",
) -> str:
    prefix = (prefix or "question-images").strip("/")
    safe_quiz_id = (quiz_id or "quiz").strip("/")
    return f"{prefix}/{user_id}/{usage_date:%Y%m%d}/{safe_quiz_id}/q{question_index + 1}.png"


def build_avatar_object_key(
    user_id: int,
    ext: str,
    prefix: str = "avatars",
    now: Optional[datetime] = None,
) -> str:
    prefix = (prefix or "avatars").strip("/")
    safe_ext = (ext or "jpg").strip().lower().lstrip(".")
    moment = now or beijing_now()
    return f"{prefix}/{user_id}/{moment:%Y%m%d}/{uuid.uuid4().hex}.{safe_ext}"


def build_public_url(key: str, settings: Settings) -> str:
    base = settings.cos_public_base_url.strip()
    if not base:
        base = (
            f"https://{settings.cos_bucket}.cos.{settings.cos_region}.myqcloud.com"
        )
    return f"{base.rstrip('/')}/{quote(key, safe='/')}"


def upload_bytes(
    data: bytes, key: str, settings: Settings, content_type: str = "image/png"
) -> str:
    """上传字节；失败只记日志并返回空字符串，由调用方决定降级方式。"""
    try:
        client = _create_client(settings)
        client.put_object(
            Bucket=settings.cos_bucket,
            Body=data,
            Key=key,
            ContentType=content_type,
            ACL="public-read",
        )
        return build_public_url(key, settings)
    except Exception as exc:  # noqa: BLE001
        logger.warning("cos_upload_failed", key=key, error=str(exc))
        return ""


def upload_image(data: bytes, key: str, settings: Settings) -> str:
    """题目配图固定为 PNG。"""
    return upload_bytes(data, key, settings, "image/png")
