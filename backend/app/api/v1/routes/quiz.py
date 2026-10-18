from fastapi import APIRouter

from app.models.common import ok
from app.models.quiz import QuizGenerateRequest
from app.services.quiz_service import generate_quiz

router = APIRouter(prefix="/quiz", tags=["quiz"])


@router.post("/generate")
def generate(req: QuizGenerateRequest) -> dict:
    quiz = generate_quiz(req)
    return ok(
        {
            "quiz_id": quiz.quiz_id,
            "title": quiz.title,
            "summary": quiz.summary,
            "questions": [q.model_dump() for q in quiz.questions],
        }
    )
