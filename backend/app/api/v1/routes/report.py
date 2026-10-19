from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool

from app.core.auth import AuthUser, get_optional_user
from app.models.common import ok
from app.models.report import ReportGenerateRequest
from app.services import persistence_service
from app.services.report_service import generate_report

router = APIRouter(prefix="/report", tags=["report"])


@router.post("/generate")
async def generate(
    req: ReportGenerateRequest,
    auth: AuthUser | None = Depends(get_optional_user),
) -> dict:
    report = await run_in_threadpool(generate_report, req)
    if auth is not None:
        await persistence_service.persist_report(auth.user_id, req, report)
    return ok(report.model_dump())
