"""users 表 CRUD。"""

from typing import Any, Optional

from app.core import db


async def get_by_openid(openid: str) -> Optional[dict[str, Any]]:
    return await db.fetch_one("SELECT * FROM users WHERE openid = %s", (openid,))


async def get_by_id(user_id: int) -> Optional[dict[str, Any]]:
    return await db.fetch_one("SELECT * FROM users WHERE id = %s", (user_id,))


async def create(openid: str, nickname: str = "学习者") -> int:
    lastrowid, _ = await db.execute(
        "INSERT INTO users (openid, nickname) VALUES (%s, %s)", (openid, nickname)
    )
    return int(lastrowid)


async def update_profile(
    user_id: int, nickname: Optional[str] = None, avatar_url: Optional[str] = None
) -> None:
    fields: list[str] = []
    args: list[Any] = []
    if nickname is not None:
        fields.append("nickname = %s")
        args.append(nickname)
    if avatar_url is not None:
        fields.append("avatar_url = %s")
        args.append(avatar_url)
    if not fields:
        return
    args.append(user_id)
    await db.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = %s", tuple(args))


async def add_coins(user_id: int, coins: int) -> None:
    await db.execute(
        "UPDATE users SET total_coins = total_coins + %s WHERE id = %s", (coins, user_id)
    )
