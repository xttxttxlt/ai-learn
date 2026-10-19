from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool

from app.core.auth import AuthUser, get_optional_user
from app.models.common import ok
from app.models.quiz import QuizGenerateRequest
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
            "questions": [q.model_dump() for q in quiz.questions],
        }
    )
