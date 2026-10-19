"""历史记录服务：闯关历史列表与详情聚合。"""

import json
from datetime import datetime
from typing import Any, Optional

from app.core.exceptions import NotFoundError
from app.models.user import QuizDetail, QuizHistoryItem, QuizHistoryList
from app.repositories import quiz_repository


def _fmt_time(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def _loads(value: Any) -> Any:
    """aiomysql 的 JSON 列可能返回 str 或已解析对象，统一兜底。"""
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return value


async def list_history(user_id: int, page: int = 1, page_size: int = 10) -> QuizHistoryList:
    page = max(1, page)
    page_size = min(max(1, page_size), 50)
    total = await quiz_repository.count_history(user_id)
    rows = await quiz_repository.list_history(user_id, (page - 1) * page_size, page_size)
    items = [
        QuizHistoryItem(
            quiz_id=row["quiz_id"],
            title=row["title"],
            accuracy=round(float(row["accuracy"])) if row["accuracy"] is not None else None,
            question_count=int(row["total_questions"]) if row["total_questions"] is not None else None,
            answered_count=int(row["answered_count"] or 0),
            current_index=int(row["current_index"] or 0),
            created_at=_fmt_time(row["created_at"]),
        )
        for row in rows
    ]
    return QuizHistoryList(items=items, total=total, page=page, page_size=page_size)


async def get_detail(user_id: int, quiz_id: str) -> QuizDetail:
    session = await quiz_repository.get_quiz_session(quiz_id, user_id)
    if session is None:
        raise NotFoundError("闯关记录不存在")

    record = await quiz_repository.get_answer_record(quiz_id, user_id)
    report_row = await quiz_repository.get_report(quiz_id, user_id)

    questions = _loads(session["questions_json"]) or []
    answer_records: Optional[Any] = _loads(record["records_json"]) if record else []
    report = _loads(report_row["report_json"]) if report_row else None
    sources = _loads(session.get("sources_json")) or []
    progress = _loads(session.get("progress_json")) or []

    return QuizDetail(
        quiz_id=session["quiz_id"],
        title=session["title"],
        summary=session["summary"] or "",
        interpretation=session.get("interpretation") or "",
        created_at=_fmt_time(session["created_at"]),
        questions=questions,
        answer_records=answer_records or [],
        report=report,
        accuracy=round(float(record["accuracy"])) if record and record["accuracy"] is not None else None,
        sources=sources,
        grounded=bool(session.get("grounded")),
        progress=progress,
        current_index=int(session.get("current_index") or 0),
    )
