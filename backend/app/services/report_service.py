import json
from typing import Any, Optional

from app.core.config import get_settings
from app.core.exceptions import ReportGenerationError, ValidationError
from app.core.logging import get_logger
from app.llm.langchain_factory import build_chat_model
from app.llm.report_chain import build_report_chain
from app.models.report import Report, ReportGenerateRequest
from app.services.scoring_service import ScoreSummary, compute_score

logger = get_logger("report_service")


def _unwrap(result: Any) -> tuple[Any, Optional[Exception]]:
    if isinstance(result, dict) and "parsed" in result:
        return result.get("parsed"), result.get("parsing_error")
    return result, None


def _validate_parsed(parsed: Any) -> None:
    if parsed is None:
        raise ReportGenerationError("模型未返回结构化报告")
    if not parsed.three_line_summary or not parsed.share_quote:
        raise ReportGenerationError("报告字段不完整")


def _build_report(parsed: Any, score: ScoreSummary) -> Report:
    """数值性内容（正确率/掌握点/薄弱点）以本地统计为准，文字性内容取自 LLM。"""
    return Report(
        accuracy=score.accuracy,
        mastered_points=score.mastered_points,
        weak_points=score.weak_points,
        three_line_summary=list(parsed.three_line_summary),
        advice=list(parsed.advice),
        share_quote=parsed.share_quote,
    )


def generate_report(request: ReportGenerateRequest, chain: Optional[Any] = None) -> Report:
    """报告主流程：本地统计 -> 调用报告链 -> 校验 -> 失败重试 -> 兜底异常。"""
    if not request.answer_records:
        raise ValidationError("答题记录不能为空")

    score = compute_score(request.questions, request.answer_records)

    settings = get_settings()
    if chain is None:
        llm = build_chat_model(settings.report_temperature, settings.report_max_tokens)
        chain = build_report_chain(llm)

    payload = {
        "topic": request.topic or "本次学习",
        "score_summary": json.dumps(score.model_dump(), ensure_ascii=False),
        "quiz_json": json.dumps(
            [q.model_dump() for q in request.questions], ensure_ascii=False
        ),
        "answer_records": json.dumps(
            [r.model_dump() for r in request.answer_records], ensure_ascii=False
        ),
    }

    attempts = settings.llm_max_retries + 1
    last_error: Optional[Exception] = None
    for attempt in range(attempts):
        try:
            result = chain.invoke(payload)
            parsed, parsing_error = _unwrap(result)
            if parsing_error is not None:
                raise parsing_error
            _validate_parsed(parsed)
            if attempt > 0:
                logger.info("report_generation_recovered", attempt=attempt)
            return _build_report(parsed, score)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning("report_generation_attempt_failed", attempt=attempt, error=str(exc))

    logger.error("report_generation_failed", error=str(last_error))
    raise ReportGenerationError()
