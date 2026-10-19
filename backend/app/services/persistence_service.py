"""持久化服务：出题/报告落库 + 金币累加。

设计约束：
1. 落库失败只记日志，绝不影响出题/报告主流程。
2. answer_records 以 quiz_id 唯一，重复提交（报告重试）走覆盖更新，
   金币只在新插入（rowcount=1）时累加，避免刷币。
"""

from app.core.logging import get_logger
from app.models.quiz import Quiz
from app.models.report import Report, ReportGenerateRequest
from app.repositories import quiz_repository, user_repository

logger = get_logger("persistence_service")

# 与前端一致：每答对一题 +10 金币
COIN_PER_CORRECT = 10


async def persist_quiz(user_id: int, quiz: Quiz) -> None:
    try:
        await quiz_repository.insert_quiz_session(
            quiz_id=quiz.quiz_id,
            user_id=user_id,
            title=quiz.title,
            summary=quiz.summary,
            user_input=quiz.user_input,
            questions=[q.model_dump() for q in quiz.questions],
            interpretation=quiz.interpretation,
            sources=[s.model_dump() for s in quiz.sources],
            grounded=quiz.grounded,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("persist_quiz_failed", quiz_id=quiz.quiz_id, error=str(exc))


async def persist_report(user_id: int, req: ReportGenerateRequest, report: Report) -> None:
    if not req.quiz_id:
        logger.warning("persist_report_skipped_no_quiz_id", user_id=user_id)
        return
    try:
        correct_count = sum(1 for r in req.answer_records if r.is_correct)
        total_questions = len(req.answer_records)

        # 报告可能先于会话落库（如出题时匿名、报告时已登录），补建最小会话满足外键
        session = await quiz_repository.get_quiz_session(req.quiz_id, user_id)
        if session is None:
            await quiz_repository.insert_quiz_session(
                quiz_id=req.quiz_id,
                user_id=user_id,
                title=req.topic or "学习闯关",
                summary="",
                user_input="",
                questions=[q.model_dump() for q in req.questions],
            )

        rowcount = await quiz_repository.insert_answer_record(
            quiz_id=req.quiz_id,
            user_id=user_id,
            records=[r.model_dump() for r in req.answer_records],
            total_questions=total_questions,
            correct_count=correct_count,
            accuracy=report.accuracy,
        )
        await quiz_repository.insert_report(
            quiz_id=req.quiz_id, user_id=user_id, report=report.model_dump()
        )
        if rowcount == 1 and correct_count > 0:
            await user_repository.add_coins(user_id, correct_count * COIN_PER_CORRECT)
    except Exception as exc:  # noqa: BLE001
        logger.warning("persist_report_failed", quiz_id=req.quiz_id, error=str(exc))
