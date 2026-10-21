"""异步出题任务：创建、后台执行、状态查询与兜底清理。"""

import asyncio
import json
import time
from typing import Any, Optional

from fastapi.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.exceptions import (
    AppError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationError,
)
from app.core.logging import get_logger
from app.llm.knowledge_base import KnowledgeScope
from app.models.quiz import Quiz, QuizGenerateRequest
from app.models.quiz_job import QuizJobCreated, QuizJobCreateRequest, QuizJobOut
from app.repositories import quiz_job_repository
from app.services import (
    image_generation_service,
    knowledge_base_service,
    persistence_service,
)
from app.services.quiz_service import generate_quiz
from app.utils.content_filter import assert_safe
from app.utils.id_generator import generate_job_id
from app.utils.text_cleaner import clean_user_input

logger = get_logger("quiz_job_service")

_running_tasks: set[asyncio.Task] = set()
_job_semaphore: Optional[asyncio.Semaphore] = None


def _get_semaphore() -> asyncio.Semaphore:
    global _job_semaphore
    if _job_semaphore is None:
        _job_semaphore = asyncio.Semaphore(get_settings().quiz_job_max_concurrency)
    return _job_semaphore


def _loads(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return value


def _error_message(exc: Exception) -> str:
    if isinstance(exc, AppError):
        return exc.message
    return "生成失败，请重试"


def _elapsed_ms(start: float) -> int:
    return max(0, int((time.perf_counter() - start) * 1000))


async def _finish_failed(
    job_id: str,
    user_id: int,
    timings: dict[str, Any],
    submitted_at: float,
    message: str,
) -> None:
    timings["total_ms"] = _elapsed_ms(submitted_at)
    logger.info(
        "quiz_job_timing",
        job_id=job_id,
        user_id=user_id,
        status="failed",
        **timings,
    )
    try:
        await quiz_job_repository.mark_failed(job_id, user_id, message, timings=timings)
    except Exception as mark_exc:  # noqa: BLE001
        logger.error("quiz_job_mark_failed_error", job_id=job_id, error=str(mark_exc))


def _submit(
    job_id: str, user_id: int, req: QuizGenerateRequest, submitted_at: float
) -> None:
    task = asyncio.create_task(_run_job(job_id, user_id, req, submitted_at))
    _running_tasks.add(task)
    task.add_done_callback(_running_tasks.discard)


async def _run_job(
    job_id: str,
    user_id: int,
    req: QuizGenerateRequest,
    submitted_at: Optional[float] = None,
) -> None:
    if submitted_at is None:
        submitted_at = time.perf_counter()
    async with _get_semaphore():
        timings: dict[str, Any] = {"queue_ms": _elapsed_ms(submitted_at)}

        try:
            await quiz_job_repository.mark_running(job_id, user_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("quiz_job_mark_running_failed", job_id=job_id, error=str(exc))
            timings["error_stage"] = "mark_running"
            await _finish_failed(job_id, user_id, timings, submitted_at, _error_message(exc))
            return

        scope_start = time.perf_counter()
        try:
            knowledge_scope = await _resolve_knowledge_scope(job_id, user_id, req)
        except Exception as exc:  # noqa: BLE001
            timings["validate_scope_ms"] = _elapsed_ms(scope_start)
            timings["error_stage"] = "validate_scope"
            logger.warning("quiz_job_scope_failed", job_id=job_id, error=str(exc))
            await _finish_failed(job_id, user_id, timings, submitted_at, _error_message(exc))
            return
        timings["validate_scope_ms"] = _elapsed_ms(scope_start)

        generate_start = time.perf_counter()
        try:
            if knowledge_scope is None:
                quiz = await run_in_threadpool(generate_quiz, req, timings=timings)
            else:
                quiz = await run_in_threadpool(
                    generate_quiz,
                    req,
                    knowledge_scope=knowledge_scope,
                    timings=timings,
                )
        except Exception as exc:  # noqa: BLE001
            timings["generate_ms"] = _elapsed_ms(generate_start)
            timings["error_stage"] = "generate"
            logger.warning("quiz_job_generation_failed", job_id=job_id, error=str(exc))
            await _finish_failed(job_id, user_id, timings, submitted_at, _error_message(exc))
            return
        timings["generate_ms"] = _elapsed_ms(generate_start)
        timings["question_count"] = len(quiz.questions)
        timings["source_count"] = len(quiz.sources)
        timings["grounded"] = quiz.grounded

        if req.generate_images and not req.use_knowledge_base:
            images_start = time.perf_counter()
            try:
                quiz = await image_generation_service.attach_images(user_id, quiz)
            except Exception as exc:  # noqa: BLE001
                logger.warning("quiz_job_images_failed", job_id=job_id, error=str(exc))
            timings["images_ms"] = _elapsed_ms(images_start)
        else:
            timings["images_ms"] = 0

        persist_start = time.perf_counter()
        try:
            await persistence_service.persist_quiz(user_id, quiz)
        except Exception as exc:  # noqa: BLE001
            logger.warning("quiz_job_persist_failed", job_id=job_id, error=str(exc))
        timings["persist_ms"] = _elapsed_ms(persist_start)

        timings["total_ms"] = _elapsed_ms(submitted_at)
        logger.info(
            "quiz_job_timing",
            job_id=job_id,
            user_id=user_id,
            status="completed",
            **timings,
        )
        try:
            await quiz_job_repository.mark_completed(
                job_id, user_id, quiz.model_dump(), timings=timings
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("quiz_job_mark_completed_failed", job_id=job_id, error=str(exc))


async def _resolve_knowledge_scope(
    job_id: str, user_id: int, req: QuizGenerateRequest
) -> Optional[KnowledgeScope]:
    """仅当请求显式开启知识库时限定单份文档，并在执行开始时重新校验。"""
    if not req.use_knowledge_base:
        return None
    if not req.document_id:
        raise ValidationError("使用知识库时必须选择一份文档")
    try:
        validated = await knowledge_base_service.validate_document_scope(
            user_id, [req.document_id]
        )
    except AppError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("quiz_job_scope_validation_failed", job_id=job_id, error=str(exc))
        raise ServiceUnavailableError() from exc
    if not validated:
        raise ValidationError("文档不可用，请重新上传")
    return KnowledgeScope(user_id=user_id, document_ids=validated)


async def create_job(user_id: int, req: QuizJobCreateRequest) -> QuizJobCreated:
    cleaned = clean_user_input(req.user_input)
    if not cleaned:
        raise ValidationError("学习内容不能为空")
    assert_safe(cleaned)

    if req.use_knowledge_base:
        await knowledge_base_service.validate_document_scope(user_id, [req.document_id])

    job_id = generate_job_id()
    generate_images = bool(req.generate_images and not req.use_knowledge_base)
    params = {
        "user_input": cleaned,
        "question_count": req.question_count,
        "difficulty": req.difficulty,
        "use_web_search": req.use_web_search,
        "use_knowledge_base": req.use_knowledge_base,
        "generate_images": generate_images,
    }
    if req.document_id:
        params["document_id"] = req.document_id
    try:
        await quiz_job_repository.create_job(job_id, user_id, req.request_id, params)
        job = await quiz_job_repository.get_by_request(user_id, req.request_id)
    except AppError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("quiz_job_create_failed", user_id=user_id, error=str(exc))
        raise ServiceUnavailableError() from exc

    if job is None:
        raise ServiceUnavailableError()

    if job["job_id"] == job_id:
        _submit(
            job_id,
            user_id,
            QuizGenerateRequest(
                user_input=cleaned,
                question_count=req.question_count,
                difficulty=req.difficulty,
                use_web_search=req.use_web_search,
                use_knowledge_base=req.use_knowledge_base,
                document_id=req.document_id,
                generate_images=generate_images,
            ),
            time.perf_counter(),
        )
    return QuizJobCreated(job_id=job["job_id"], status=job["status"])


async def get_job(user_id: int, job_id: str) -> QuizJobOut:
    job = await quiz_job_repository.get_job(job_id, user_id)
    if job is None:
        raise NotFoundError("任务不存在")

    if job["status"] == "running":
        timed_out = await quiz_job_repository.fail_if_timed_out(
            job_id, user_id, get_settings().quiz_job_timeout_seconds
        )
        if timed_out:
            job = await quiz_job_repository.get_job(job_id, user_id) or job

    status = job["status"]
    quiz: Optional[Quiz] = None
    if status == "completed":
        result = _loads(job.get("result_json"))
        quiz = Quiz.model_validate(result) if result else None
    return QuizJobOut(
        job_id=job["job_id"],
        status=status,
        quiz=quiz,
        error=job.get("error_message") if status == "failed" else None,
    )


async def cleanup_on_startup() -> None:
    try:
        count = await quiz_job_repository.fail_in_progress("服务重启，任务已中断，请重新生成")
    except Exception as exc:  # noqa: BLE001
        logger.warning("quiz_job_startup_cleanup_failed", error=str(exc))
        return
    if count:
        logger.info("quiz_job_startup_cleaned", count=count)
