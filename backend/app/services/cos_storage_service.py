"""腾讯云 COS 图片上传：公有读桶、固定 URL。"""

from datetime import date
from urllib.parse import quote

from app.core.config import Settings
from app.core.logging import get_logger

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


def build_public_url(key: str, settings: Settings) -> str:
    base = settings.cos_public_base_url.strip()
    if not base:
        base = (
            f"https://{settings.cos_bucket}.cos.{settings.cos_region}.myqcloud.com"
        )
    return f"{base.rstrip('/')}/{quote(key, safe='/')}"


def upload_image(data: bytes, key: str, settings: Settings) -> str:
    """上传图片字节；失败只记日志并返回空字符串，由调用方按单题降级。"""
    try:
        client = _create_client(settings)
        client.put_object(
            Bucket=settings.cos_bucket,
            Body=data,
            Key=key,
            ContentType="image/png",
            ACL="public-read",
        )
        return build_public_url(key, settings)
    except Exception as exc:  # noqa: BLE001
        logger.warning("cos_upload_failed", key=key, error=str(exc))
        return ""
