from fastapi import APIRouter

from app.models.common import ok

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return ok({"status": "healthy"})
