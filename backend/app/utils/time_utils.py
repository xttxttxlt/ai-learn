"""北京时间工具：不依赖操作系统时区或 tzdata。"""

from datetime import date, datetime, timedelta, timezone

BEIJING_TZ = timezone(timedelta(hours=8))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_beijing(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(BEIJING_TZ)


def beijing_now() -> datetime:
    return to_beijing(_utc_now())


def beijing_today() -> date:
    return beijing_now().date()
