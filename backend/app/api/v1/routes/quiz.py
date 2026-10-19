from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool

from app.core.auth import AuthUser, get_current_user, get_optional_user
from app.models.common import ok
from app.models.quiz import QuizGenerateRequest
from app.models.report import QuizProgressSaveRequest
from app.repositories import quiz_repository
from app.services import persistence_service
from app.services.quiz_service import generate_quiz

router = APIRouter(prefix="/quiz", tags=["quiz"])


@router.post("/generate")
async def generate(
    req: QuizGenerateRequest,
    auth: AuthUser | None = Depends(get_optional_user),
) -> dict:
    # LLM 调用是同步阻塞的，放入线程池，行为与原同步路由一致
    quiz = await run_in_threadpool(generate_quiz, req)
    if auth is not None:
        await persistence_service.persist_quiz(auth.user_id, quiz)
    return ok(
        {
            "quiz_id": quiz.quiz_id,
            "title": quiz.title,
            "summary": quiz.summary,
            "interpretation": quiz.interpretation,
            "grounded": quiz.grounded,
            "sources": [s.model_dump() for s in quiz.sources],
            "questions": [q.model_dump() for q in quiz.questions],
        }
    )


@router.post("/progress")
async def save_progress(
    req: QuizProgressSaveRequest, auth: AuthUser = Depends(get_current_user)
) -> dict:
    """断点续答进度上报：把已答记录与当前题号落到本人 quiz_sessions。"""
    await quiz_repository.save_progress(
        quiz_id=req.quiz_id,
        user_id=auth.user_id,
        index=req.index,
        records=[r.model_dump() for r in req.records],
    )
    return ok(None)
