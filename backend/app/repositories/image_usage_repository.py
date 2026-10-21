"""每日配图用量：按用户与自然日查询、预留与退还。"""

from datetime import date

from app.core import db


async def get_count(user_id: int, usage_date: date) -> int:
    row = await db.fetch_one(
        """SELECT image_count FROM image_generation_usage
           WHERE user_id = %s AND usage_date = %s""",
        (user_id, usage_date),
    )
    return int(row["image_count"]) if row else 0


async def add_count(user_id: int, usage_date: date, delta: int) -> None:
    """正数为预留额度，负数为失败退还；退还时用 GREATEST 防止计数为负。"""
    if delta == 0:
        return
    if delta > 0:
        await db.execute(
            """INSERT INTO image_generation_usage (user_id, usage_date, image_count)
               VALUES (%s, %s, %s)
               ON DUPLICATE KEY UPDATE image_count = image_count + VALUES(image_count)""",
            (user_id, usage_date, delta),
        )
        return
    await db.execute(
        """UPDATE image_generation_usage
           SET image_count = GREATEST(0, image_count - %s)
           WHERE user_id = %s AND usage_date = %s""",
        (-delta, user_id, usage_date),
    )
