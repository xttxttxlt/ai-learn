"""quiz_jobs 表的创建、状态流转与查询。"""

import json
from typing import Any, Optional

from app.core import db


async def create_job(
    job_id: str, user_id: int, request_id: str, params: dict[str, Any]
) -> int:
    """插入任务；同一用户同一 request_id 重复插入时保持既有行不变。返回 rowcount。"""
    _, rowcount = await db.execute(
        """INSERT INTO quiz_jobs (job_id, user_id, request_id, status, params_json)
           VALUES (%s, %s, %s, 'pending', %s)
           ON DUPLICATE KEY UPDATE job_id = job_id""",
        (job_id, user_id, request_id, json.dumps(params, ensure_ascii=False)),
    )
    return rowcount


async def get_by_request(user_id: int, request_id: str) -> Optional[dict[str, Any]]:
    return await db.fetch_one(
        "SELECT * FROM quiz_jobs WHERE user_id = %s AND request_id = %s",
        (user_id, request_id),
    )


async def get_job(job_id: str, user_id: int) -> Optional[dict[str, Any]]:
    return await db.fetch_one(
        "SELECT * FROM quiz_jobs WHERE job_id = %s AND user_id = %s",
        (job_id, user_id),
    )


async def mark_running(job_id: str, user_id: int) -> int:
    _, rowcount = await db.execute(
        """UPDATE quiz_jobs SET status = 'running'
           WHERE job_id = %s AND user_id = %s AND status = 'pending'""",
        (job_id, user_id),
    )
    return rowcount


def _timings_json(timings: Optional[dict[str, Any]]) -> Optional[str]:
    if timings is None:
        return None
    return json.dumps(timings, ensure_ascii=False)


async def mark_completed(
    job_id: str,
    user_id: int,
    result: dict[str, Any],
    timings: Optional[dict[str, Any]] = None,
) -> int:
    _, rowcount = await db.execute(
        """UPDATE quiz_jobs
           SET status = 'completed', result_json = %s, error_message = NULL,
               timings_json = %s, finished_at = NOW()
           WHERE job_id = %s AND user_id = %s AND status IN ('pending', 'running')""",
        (
            json.dumps(result, ensure_ascii=False),
            _timings_json(timings),
            job_id,
            user_id,
        ),
    )
    return rowcount


async def mark_failed(
    job_id: str,
    user_id: int,
    error_message: str,
    timings: Optional[dict[str, Any]] = None,
) -> int:
    _, rowcount = await db.execute(
        """UPDATE quiz_jobs
           SET status = 'failed', error_message = %s, timings_json = %s,
               finished_at = NOW()
           WHERE job_id = %s AND user_id = %s AND status IN ('pending', 'running')""",
        (error_message[:500], _timings_json(timings), job_id, user_id),
    )
    return rowcount


async def fail_if_timed_out(job_id: str, user_id: int, timeout_seconds: int) -> int:
    """仅当任务仍在 running 且创建时间早于超时阈值时置为 failed（条件更新）。"""
    _, rowcount = await db.execute(
        """UPDATE quiz_jobs
           SET status = 'failed', error_message = %s, finished_at = NOW()
           WHERE job_id = %s AND user_id = %s AND status = 'running'
             AND created_at < DATE_SUB(NOW(), INTERVAL %s SECOND)""",
        ("生成超时，请重试", job_id, user_id, timeout_seconds),
    )
    return rowcount


async def fail_in_progress(error_message: str) -> int:
    """启动清理：把残留的 pending / running 任务统一置为 failed。"""
    _, rowcount = await db.execute(
        """UPDATE quiz_jobs
           SET status = 'failed', error_message = %s, finished_at = NOW()
           WHERE status IN ('pending', 'running')""",
        (error_message[:500],),
    )
    return rowcount
