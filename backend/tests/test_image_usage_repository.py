from datetime import date

from app.repositories import image_usage_repository as repo
from tests.fake_db import FakeDB

DAY = date(2026, 10, 21)


async def test_get_count_returns_zero_when_no_row(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.fetch_one_queue = [None]

    assert await repo.get_count(7, DAY) == 0
    sql, args = fake.fetch_one_calls[0]
    assert "FROM image_generation_usage" in sql
    assert "user_id = %s" in sql
    assert "usage_date = %s" in sql
    assert args == (7, DAY)


async def test_get_count_returns_number(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.fetch_one_queue = [{"image_count": 12}]

    assert await repo.get_count(7, DAY) == 12


async def test_add_positive_count_uses_upsert(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.execute_queue = [(1, 1)]

    await repo.add_count(7, DAY, 5)

    sql, args = fake.executed[0]
    assert "INSERT INTO image_generation_usage" in sql
    assert "ON DUPLICATE KEY UPDATE" in sql
    assert "image_count = image_count + VALUES(image_count)" in sql
    assert args == (7, DAY, 5)


async def test_add_negative_count_refunds_with_floor(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.execute_queue = [(0, 1)]

    await repo.add_count(7, DAY, -3)

    sql, args = fake.executed[0]
    assert "UPDATE image_generation_usage" in sql
    assert "GREATEST(0, image_count - %s)" in sql
    assert "user_id = %s" in sql
    assert "usage_date = %s" in sql
    assert args == (3, 7, DAY)


async def test_add_zero_count_skips_database(monkeypatch):
    fake = FakeDB().install(monkeypatch)

    await repo.add_count(7, DAY, 0)

    assert fake.executed == []
