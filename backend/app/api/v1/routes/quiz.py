from fastapi import APIRouter, Depends

from app.core.auth import AuthUser, get_current_user
from app.models.common import ok
from app.models.quiz_job import QuizJobCreateRequest
from app.models.report import QuizProgressSaveRequest
from app.repositories import quiz_repository
from app.services import quiz_job_service

router = APIRouter(prefix="/quiz", tags=["quiz"])


@router.post("/jobs")
async def create_job(
    req: QuizJobCreateRequest, auth: AuthUser = Depends(get_current_user)
) -> dict:
    created = await quiz_job_service.create_job(auth.user_id, req)
    return ok(created.model_dump())


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, auth: AuthUser = Depends(get_current_user)) -> dict:
    job = await quiz_job_service.get_job(auth.user_id, job_id)
    return ok(job.model_dump())


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
