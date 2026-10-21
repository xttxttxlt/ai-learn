"""异步出题任务：创建、后台执行、状态查询与兜底清理。"""

import asyncio
import json
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
from app.repositories import knowledge_document_repository, quiz_job_repository
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


def _submit(job_id: str, user_id: int, req: QuizGenerateRequest) -> None:
    task = asyncio.create_task(_run_job(job_id, user_id, req))
    _running_tasks.add(task)
    task.add_done_callback(_running_tasks.discard)


async def _run_job(job_id: str, user_id: int, req: QuizGenerateRequest) -> None:
    async with _get_semaphore():
        try:
            await quiz_job_repository.mark_running(job_id, user_id)
            knowledge_scope = await _resolve_knowledge_scope(job_id, user_id, req)
            if knowledge_scope is None:
                quiz = await run_in_threadpool(generate_quiz, req)
            else:
                quiz = await run_in_threadpool(
                    generate_quiz, req, knowledge_scope=knowledge_scope
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("quiz_job_generation_failed", job_id=job_id, error=str(exc))
            try:
                await quiz_job_repository.mark_failed(job_id, user_id, _error_message(exc))
            except Exception as mark_exc:  # noqa: BLE001
                logger.error("quiz_job_mark_failed_error", job_id=job_id, error=str(mark_exc))
            return

        if req.generate_images and not req.document_ids:
            try:
                quiz = await image_generation_service.attach_images(user_id, quiz)
            except Exception as exc:  # noqa: BLE001
                logger.warning("quiz_job_images_failed", job_id=job_id, error=str(exc))

        try:
            await persistence_service.persist_quiz(user_id, quiz)
        except Exception as exc:  # noqa: BLE001
            logger.warning("quiz_job_persist_failed", job_id=job_id, error=str(exc))

        try:
            await quiz_job_repository.mark_completed(job_id, user_id, quiz.model_dump())
        except Exception as exc:  # noqa: BLE001
            logger.error("quiz_job_mark_completed_failed", job_id=job_id, error=str(exc))


async def _resolve_knowledge_scope(
    job_id: str, user_id: int, req: QuizGenerateRequest
) -> Optional[KnowledgeScope]:
    """文档范围任务固定限定文档；首页任务仅在存在已就绪文档时启用知识库。"""
    document_ids = list(req.document_ids or [])
    if document_ids:
        return KnowledgeScope(user_id=user_id, document_ids=document_ids)
    try:
        ready_count = await knowledge_document_repository.count_ready(user_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "quiz_job_ready_lookup_failed", job_id=job_id, error=str(exc)
        )
        return None
    if ready_count > 0:
        return KnowledgeScope(user_id=user_id)
    return None


async def create_job(user_id: int, req: QuizJobCreateRequest) -> QuizJobCreated:
    cleaned = clean_user_input(req.user_input)
    if not cleaned:
        raise ValidationError("学习内容不能为空")
    assert_safe(cleaned)

    document_ids = list(req.document_ids or [])
    if document_ids:
        document_ids = await knowledge_base_service.validate_document_scope(
            user_id, document_ids
        )

    job_id = generate_job_id()
    generate_images = bool(req.generate_images and not document_ids)
    params = {
        "user_input": cleaned,
        "question_count": req.question_count,
        "difficulty": req.difficulty,
    }
    if generate_images:
        params["generate_images"] = True
    if document_ids:
        params["document_ids"] = document_ids
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
                document_ids=document_ids,
                generate_images=generate_images,
            ),
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
