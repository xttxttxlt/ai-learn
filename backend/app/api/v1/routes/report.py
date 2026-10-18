from fastapi import APIRouter

from app.models.common import ok
from app.models.report import ReportGenerateRequest
from app.services.report_service import generate_report

router = APIRouter(prefix="/report", tags=["report"])


@router.post("/generate")
def generate(req: ReportGenerateRequest) -> dict:
    report = generate_report(req)
    return ok(report.model_dump())
