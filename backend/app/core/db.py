"""MySQL 连接池与基础访问helper（aiomysql）。

应用启动时 init_db() 创建连接池，关闭时 close_db() 释放；
初始化失败只记日志不阻断启动（匿名模式仍可用）。
"""

from pathlib import Path
from typing import Any, Optional

import aiomysql

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("db")

# sql/init_mysql.sql（backend/ 上一级）
SCHEMA_FILE = Path(__file__).resolve().parent.parent.parent.parent / "sql" / "init_mysql.sql"

_pool: Optional[aiomysql.Pool] = None


def get_pool() -> Optional[aiomysql.Pool]:
    return _pool


async def _run_schema_init() -> None:
    """执行 sql/init_mysql.sql 中的建库建表语句（全部 IF NOT EXISTS，可重复执行）。"""
    settings = get_settings()
    statements = [
        s.strip()
        for s in SCHEMA_FILE.read_text(encoding="utf-8").split(";")
        if s.strip()
    ]
    conn = await aiomysql.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        charset=settings.mysql_charset,
        autocommit=True,
    )
    try:
        async with conn.cursor() as cur:
            # 幂等 DDL 在对象已存在时会产生 Note；只在本初始化连接屏蔽，避免启动日志噪声
            await cur.execute("SET sql_notes = 0")
            for stmt in statements:
                await cur.execute(stmt)
    finally:
        conn.close()


async def init_db() -> None:
    global _pool
    settings = get_settings()
    try:
        if settings.mysql_auto_init:
            await _run_schema_init()
        _pool = await aiomysql.create_pool(
            host=settings.mysql_host,
            port=settings.mysql_port,
            user=settings.mysql_user,
            password=settings.mysql_password,
            db=settings.mysql_database,
            charset=settings.mysql_charset,
            minsize=settings.mysql_pool_minsize,
            maxsize=settings.mysql_pool_maxsize,
            autocommit=True,
        )
        logger.info("mysql_pool_ready", host=settings.mysql_host, db=settings.mysql_database)
    except Exception as exc:  # noqa: BLE001
        _pool = None
        logger.error("mysql_init_failed", error=str(exc))


async def close_db() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        await _pool.wait_closed()
        _pool = None


class DbUnavailableError(RuntimeError):
    pass


def _require_pool() -> aiomysql.Pool:
    if _pool is None:
        raise DbUnavailableError("MySQL 连接池未初始化")
    return _pool


async def fetch_all(sql: str, args: Optional[tuple] = None) -> list[dict[str, Any]]:
    async with _require_pool().acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(sql, args)
            return list(await cur.fetchall())


async def fetch_one(sql: str, args: Optional[tuple] = None) -> Optional[dict[str, Any]]:
    async with _require_pool().acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(sql, args)
            return await cur.fetchone()


async def execute(sql: str, args: Optional[tuple] = None) -> tuple[int, int]:
    """执行写语句，返回 (lastrowid, rowcount)。ON DUPLICATE 更新时 rowcount=2。"""
    async with _require_pool().acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, args)
            return cur.lastrowid, cur.rowcount
