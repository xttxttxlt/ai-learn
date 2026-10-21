"""用户服务：微信登录（code2session + 自动注册 + JWT）、档案查询与更新。"""

from typing import Optional

import httpx

from app.core.auth import create_token
from app.core.config import get_settings
from app.core.exceptions import NotFoundError, WechatLoginError
from app.core.logging import get_logger
from app.models.user import ImageQuotaOut, LoginResponse, ProfileOut, UserOut
from app.repositories import image_usage_repository, quiz_repository, user_repository
from app.utils.time_utils import beijing_today

logger = get_logger("user_service")

CODE2SESSION_URL = "https://api.weixin.qq.com/sns/jscode2session"


async def code2session(code: str) -> str:
    """调微信 jscode2session 换取 openid；失败抛 WechatLoginError。"""
    settings = get_settings()
    if not settings.wechat_appid or not settings.wechat_appsecret:
        logger.error("wechat_not_configured")
        raise WechatLoginError("微信登录未配置")
    params = {
        "appid": settings.wechat_appid,
        "secret": settings.wechat_appsecret,
        "js_code": code,
        "grant_type": "authorization_code",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(CODE2SESSION_URL, params=params)
            data = resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.error("code2session_request_failed", error=str(exc))
        raise WechatLoginError()
    openid = data.get("openid")
    if not openid:
        logger.warning("code2session_failed", errcode=data.get("errcode"), errmsg=data.get("errmsg"))
        raise WechatLoginError()
    return str(openid)


def _user_out(row: dict) -> UserOut:
    return UserOut(
        id=int(row["id"]),
        nickname=row["nickname"],
        avatar_url=row["avatar_url"] or "",
        total_coins=int(row["total_coins"]),
    )


async def login(code: str) -> LoginResponse:
    """登录主流程：code -> openid -> 查用户（不存在则自动注册）-> 签发 JWT。"""
    openid = await code2session(code)
    row = await user_repository.get_by_openid(openid)
    if row is None:
        user_id = await user_repository.create(openid)
        row = await user_repository.get_by_id(user_id)
        if row is None:  # 理论上不会发生
            raise WechatLoginError()
        logger.info("user_registered", user_id=user_id)
    token = create_token(int(row["id"]), openid)
    return LoginResponse(token=token, user=_user_out(row))


def _image_quota_out(
    usage_date, used: int, limit: int, available: bool
) -> ImageQuotaOut:
    return ImageQuotaOut(
        usage_date=usage_date.isoformat(),
        used=used,
        limit=limit,
        remaining=max(0, limit - used),
        available=available,
    )


async def get_profile(user_id: int) -> ProfileOut:
    row = await user_repository.get_by_id(user_id)
    if row is None:
        raise NotFoundError("用户不存在")
    stats = await quiz_repository.get_stats(user_id)

    limit = get_settings().image_daily_limit
    usage_date = beijing_today()
    try:
        used = await image_usage_repository.get_count(user_id, usage_date)
        quota = _image_quota_out(usage_date, used, limit, available=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("image_quota_read_failed", user_id=user_id, error=str(exc))
        quota = _image_quota_out(usage_date, 0, limit, available=False)

    return ProfileOut(
        id=int(row["id"]),
        nickname=row["nickname"],
        avatar_url=row["avatar_url"] or "",
        total_coins=int(row["total_coins"]),
        quiz_count=stats["quiz_count"],
        correct_count=stats["correct_count"],
        average_accuracy=stats["average_accuracy"],
        image_quota=quota,
    )


async def update_profile(
    user_id: int, nickname: Optional[str] = None, avatar_url: Optional[str] = None
) -> ProfileOut:
    row = await user_repository.get_by_id(user_id)
    if row is None:
        raise NotFoundError("用户不存在")
    await user_repository.update_profile(user_id, nickname=nickname, avatar_url=avatar_url)
    return await get_profile(user_id)
