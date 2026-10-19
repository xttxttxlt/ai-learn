"""quiz_sessions / answer_records / reports 三表的写入与聚合查询。"""

import json
from typing import Any, Optional

from app.core import db


async def insert_quiz_session(
    quiz_id: str,
    user_id: int,
    title: str,
    summary: str,
    user_input: str,
    questions: list[dict],
    interpretation: str = "",
    sources: Optional[list[dict]] = None,
    grounded: bool = False,
) -> None:
    await db.execute(
        """INSERT INTO quiz_sessions
               (quiz_id, user_id, title, summary, user_input, questions_json,
                interpretation, sources_json, grounded)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON DUPLICATE KEY UPDATE user_id = VALUES(user_id)""",
        (
            quiz_id,
            user_id,
            title,
            summary,
            user_input,
            json.dumps(questions, ensure_ascii=False),
            interpretation,
            json.dumps(sources or [], ensure_ascii=False),
            int(bool(grounded)),
        ),
    )


async def get_quiz_session(quiz_id: str, user_id: int) -> Optional[dict[str, Any]]:
    return await db.fetch_one(
        "SELECT * FROM quiz_sessions WHERE quiz_id = %s AND user_id = %s", (quiz_id, user_id)
    )


async def insert_answer_record(
    quiz_id: str,
    user_id: int,
    records: list[dict],
    total_questions: int,
    correct_count: int,
    accuracy: float,
) -> int:
    """返回 rowcount：1=新插入，2=覆盖更新（用于避免金币重复累加）。"""
    _, rowcount = await db.execute(
        """INSERT INTO answer_records
               (quiz_id, user_id, records_json, total_questions, correct_count, accuracy)
           VALUES (%s, %s, %s, %s, %s, %s)
           ON DUPLICATE KEY UPDATE
               records_json = VALUES(records_json),
               total_questions = VALUES(total_questions),
               correct_count = VALUES(correct_count),
               accuracy = VALUES(accuracy)""",
        (
            quiz_id,
            user_id,
            json.dumps(records, ensure_ascii=False),
            total_questions,
            correct_count,
            accuracy,
        ),
    )
    return rowcount


async def insert_report(quiz_id: str, user_id: int, report: dict) -> None:
    await db.execute(
        """INSERT INTO reports (quiz_id, user_id, report_json)
           VALUES (%s, %s, %s)
           ON DUPLICATE KEY UPDATE report_json = VALUES(report_json)""",
        (quiz_id, user_id, json.dumps(report, ensure_ascii=False)),
    )


async def save_progress(quiz_id: str, user_id: int, index: int, records: list[dict]) -> None:
    """断点续答进度落库（仅更新本人会话；不存在则不更新）。"""
    await db.execute(
        """UPDATE quiz_sessions
           SET progress_json = %s, current_index = %s
           WHERE quiz_id = %s AND user_id = %s""",
        (json.dumps(records, ensure_ascii=False), index, quiz_id, user_id),
    )


async def get_stats(user_id: int) -> dict[str, Any]:
    """聚合：闯关次数（以完成答题为准）、累计答对题数、平均正确率。"""
    row = await db.fetch_one(
        """SELECT COUNT(*) AS quiz_count,
                  COALESCE(SUM(correct_count), 0) AS correct_count,
                  COALESCE(AVG(accuracy), 0) AS avg_accuracy
           FROM answer_records WHERE user_id = %s""",
        (user_id,),
    )
    if not row:
        return {"quiz_count": 0, "correct_count": 0, "average_accuracy": 0}
    return {
        "quiz_count": int(row["quiz_count"]),
        "correct_count": int(row["correct_count"]),
        "average_accuracy": round(float(row["avg_accuracy"])),
    }


async def list_history(user_id: int, offset: int, limit: int) -> list[dict[str, Any]]:
    return await db.fetch_all(
        """SELECT qs.quiz_id, qs.title, qs.created_at,
                  ar.accuracy,
                  JSON_LENGTH(qs.questions_json) AS total_questions,
                  COALESCE(JSON_LENGTH(qs.progress_json), 0) AS answered_count,
                  qs.current_index
           FROM quiz_sessions qs
           LEFT JOIN answer_records ar ON ar.quiz_id = qs.quiz_id
           WHERE qs.user_id = %s
           ORDER BY qs.created_at DESC, qs.id DESC
           LIMIT %s OFFSET %s""",
        (user_id, limit, offset),
    )


async def count_history(user_id: int) -> int:
    row = await db.fetch_one(
        "SELECT COUNT(*) AS total FROM quiz_sessions WHERE user_id = %s", (user_id,)
    )
    return int(row["total"]) if row else 0


async def get_answer_record(quiz_id: str, user_id: int) -> Optional[dict[str, Any]]:
    return await db.fetch_one(
        "SELECT * FROM answer_records WHERE quiz_id = %s AND user_id = %s", (quiz_id, user_id)
    )


async def get_report(quiz_id: str, user_id: int) -> Optional[dict[str, Any]]:
    return await db.fetch_one(
        "SELECT * FROM reports WHERE quiz_id = %s AND user_id = %s", (quiz_id, user_id)
    )
