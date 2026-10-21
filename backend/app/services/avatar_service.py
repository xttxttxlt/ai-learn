"""用户头像：图片格式校验、COS 转存与用户档案更新。"""

from typing import Optional

from fastapi import UploadFile

from app.core.config import Settings, get_settings
from app.core.exceptions import ServiceUnavailableError, ValidationError
from app.core.logging import get_logger
from app.repositories import user_repository
from app.services import cos_storage_service

logger = get_logger("avatar_service")

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_JPEG_SIGNATURE = b"\xff\xd8\xff"


def detect_image_format(data: bytes) -> Optional[tuple[str, str]]:
    """按魔数识别头像格式；不信任客户端文件名或 Content-Type。"""
    if data.startswith(_PNG_SIGNATURE):
        return "png", "image/png"
    if data.startswith(_JPEG_SIGNATURE):
        return "jpg", "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp", "image/webp"
    return None


async def update_avatar(
    user_id: int,
    upload: UploadFile,
    settings: Optional[Settings] = None,
) -> str:
    settings = settings or get_settings()
    if not settings.cos_ready:
        raise ServiceUnavailableError("头像服务暂不可用，请稍后重试")

    data = await upload.read(settings.avatar_max_file_bytes + 1)
    if not data:
        raise ValidationError("请选择有效的头像图片")
    if len(data) > settings.avatar_max_file_bytes:
        raise ValidationError(f"头像图片不能超过 {settings.avatar_max_file_mb}MB")

    detected = detect_image_format(data)
    if detected is None:
        raise ValidationError("头像仅支持 JPG、PNG 或 WebP 格式")
    ext, content_type = detected

    key = cos_storage_service.build_avatar_object_key(
        user_id, ext, settings.cos_avatar_prefix
    )
    url = cos_storage_service.upload_bytes(data, key, settings, content_type)
    if not url:
        raise ServiceUnavailableError("头像上传失败，请稍后重试")

    try:
        await user_repository.update_profile(user_id, avatar_url=url)
    except Exception as exc:  # noqa: BLE001
        logger.warning("avatar_profile_update_failed", user_id=user_id, error=str(exc))
        raise ServiceUnavailableError("头像保存失败，请稍后重试") from exc
    return url
