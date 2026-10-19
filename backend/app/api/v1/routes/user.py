from fastapi import APIRouter, Depends, Query

from app.core.auth import AuthUser, get_current_user
from app.models.common import ok
from app.models.user import LoginRequest, ProfileUpdateRequest
from app.services import history_service, user_service

router = APIRouter(prefix="/user", tags=["user"])


@router.post("/login")
async def login(req: LoginRequest) -> dict:
    result = await user_service.login(req.code)
    return ok(result.model_dump())


@router.get("/profile")
async def get_profile(auth: AuthUser = Depends(get_current_user)) -> dict:
    profile = await user_service.get_profile(auth.user_id)
    return ok(profile.model_dump())


@router.put("/profile")
async def update_profile(
    req: ProfileUpdateRequest, auth: AuthUser = Depends(get_current_user)
) -> dict:
    profile = await user_service.update_profile(
        auth.user_id, nickname=req.nickname, avatar_url=req.avatar_url
    )
    return ok(profile.model_dump())


@router.get("/quizzes")
async def list_quizzes(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    auth: AuthUser = Depends(get_current_user),
) -> dict:
    result = await history_service.list_history(auth.user_id, page, page_size)
    return ok(result.model_dump())


@router.get("/quizzes/{quiz_id}")
async def quiz_detail(quiz_id: str, auth: AuthUser = Depends(get_current_user)) -> dict:
    detail = await history_service.get_detail(auth.user_id, quiz_id)
    return ok(detail.model_dump())
