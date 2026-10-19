"""JWT 生成/解析与鉴权依赖（强制 + 可选两种模式）。"""

from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Request
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.exceptions import UnauthorizedError

ALGORITHM = "HS256"


class AuthUser(BaseModel):
    user_id: int
    openid: str


def create_token(user_id: int, openid: str) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        "openid": openid,
        "iat": now,
        "exp": now + timedelta(days=settings.jwt_expire_days),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, get_settings().jwt_secret, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None


def _extract_token(request: Request) -> Optional[str]:
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        token = header[len("Bearer ") :].strip()
        return token or None
    return None


def _auth_user_from(request: Request) -> Optional[AuthUser]:
    token = _extract_token(request)
    if not token:
        return None
    payload = decode_token(token)
    if not payload or "user_id" not in payload:
        return None
    return AuthUser(user_id=int(payload["user_id"]), openid=str(payload.get("openid", "")))


async def get_current_user(request: Request) -> AuthUser:
    """强制鉴权：无 token 或 token 无效时抛 4010。"""
    user = _auth_user_from(request)
    if user is None:
        raise UnauthorizedError()
    return user


async def get_optional_user(request: Request) -> Optional[AuthUser]:
    """可选鉴权：无 token / token 无效均返回 None，不报错。"""
    return _auth_user_from(request)
