from datetime import date, datetime, timedelta, timezone

from app.utils import time_utils


def test_beijing_now_converts_utc_to_east_eight():
    fixed_utc = datetime(2026, 10, 21, 7, 28, 20, tzinfo=timezone.utc)

    converted = time_utils.to_beijing(fixed_utc)

    assert converted.utcoffset() == timedelta(hours=8)
    assert converted == datetime(
        2026, 10, 21, 15, 28, 20, tzinfo=time_utils.BEIJING_TZ
    )


def test_beijing_today_crosses_day_at_utc_1600(monkeypatch):
    fixed_utc = datetime(2026, 10, 21, 16, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(time_utils, "_utc_now", lambda: fixed_utc)

    assert time_utils.beijing_now() == datetime(
        2026, 10, 22, 0, 0, 0, tzinfo=time_utils.BEIJING_TZ
    )
    assert time_utils.beijing_today() == date(2026, 10, 22)


def test_beijing_today_keeps_same_day_at_utc_1559(monkeypatch):
    fixed_utc = datetime(2026, 10, 21, 15, 59, 59, tzinfo=timezone.utc)
    monkeypatch.setattr(time_utils, "_utc_now", lambda: fixed_utc)

    assert time_utils.beijing_today() == date(2026, 10, 21)
