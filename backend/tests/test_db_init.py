import re
from pathlib import Path

import pytest

from app.core import db

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


class FakeCursor:
    def __init__(self):
        self.statements: list[str] = []

    async def execute(self, stmt):
        self.statements.append(stmt)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeConnection:
    def __init__(self):
        self.cursor_obj = FakeCursor()
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def close(self):
        self.closed = True


class FakeSettings:
    mysql_host = "localhost"
    mysql_port = 3306
    mysql_user = "root"
    mysql_password = ""
    mysql_charset = "utf8mb4"


async def test_schema_init_disables_sql_notes(monkeypatch, tmp_path):
    schema = tmp_path / "schema.sql"
    schema.write_text(
        "CREATE TABLE IF NOT EXISTS a (id INT);\n"
        "CREATE TABLE IF NOT EXISTS b (id INT);\n",
        encoding="utf-8",
    )
    connection = FakeConnection()

    async def fake_connect(**kwargs):
        return connection

    monkeypatch.setattr(db, "SCHEMA_FILE", schema)
    monkeypatch.setattr(db, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(db.aiomysql, "connect", fake_connect)

    await db._run_schema_init()

    assert connection.cursor_obj.statements[0] == "SET sql_notes = 0"
    assert connection.cursor_obj.statements[1].startswith("CREATE TABLE IF NOT EXISTS a")
    assert connection.cursor_obj.statements[2].startswith("CREATE TABLE IF NOT EXISTS b")
    assert connection.closed is True


@pytest.mark.parametrize(
    "relative_path",
    [
        "init_mysql.sql",
        "migrations/20261020_add_quiz_grounding.sql",
        "migrations/20261021_add_image_generation.sql",
    ],
)
def test_sql_files_have_no_integer_display_width(relative_path):
    text = (SQL_DIR / relative_path).read_text(encoding="utf-8")

    assert not re.search(
        r"\b(?:TINYINT|SMALLINT|MEDIUMINT|INT|INTEGER|BIGINT)\s*\(\s*\d+\s*\)",
        text,
        re.IGNORECASE,
    )


@pytest.mark.parametrize(
    "relative_path",
    ["init_mysql.sql", "migrations/20261021_add_image_generation.sql"],
)
def test_image_usage_table_is_created_idempotently(relative_path):
    text = (SQL_DIR / relative_path).read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS image_generation_usage" in text
    assert "uk_image_usage_user_date" in text
    assert "COMMENT='每日配图生成用量表'" in text
