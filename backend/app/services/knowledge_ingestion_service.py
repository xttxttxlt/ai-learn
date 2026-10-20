"""异步建库服务：解析 -> 分块 -> Embedding -> 写入 Chroma -> 更新状态。

上传接口只负责落盘与创建 pending 记录；本服务在后台执行建库，
状态沿 pending -> processing -> ready/failed 单向流转。
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from fastapi.concurrency import run_in_threadpool

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.llm.document_parser import DocumentParseError, parse_document
from app.llm.knowledge_base import (
    EmbeddingConfigError,
    EmbeddingServiceError,
    build_vector_store,
)
from app.repositories import knowledge_document_repository

logger = get_logger("knowledge_ingestion_service")

RESTART_ERROR = "服务重启，处理已中断，请重新上传"
GENERIC_ERROR = "文档处理失败，请稍后重试"

_running_tasks: set[asyncio.Task] = set()
_ingestion_semaphore: Optional[asyncio.Semaphore] = None


def _get_semaphore(settings: Settings) -> asyncio.Semaphore:
    global _ingestion_semaphore
    if _ingestion_semaphore is None:
        _ingestion_semaphore = asyncio.Semaphore(
            max(1, settings.kb_ingestion_concurrency)
        )
    return _ingestion_semaphore


def _readable_error(exc: Exception) -> str:
    if isinstance(
        exc, (DocumentParseError, EmbeddingConfigError, EmbeddingServiceError)
    ):
        message = str(exc).strip()
        if message:
            return message[:500]
    return GENERIC_ERROR


def _safe_delete_vectors(store: Any, user_id: int, doc_id: str) -> None:
    try:
        store.delete_document(user_id, doc_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "knowledge_vector_cleanup_failed",
            user_id=user_id,
            doc_id=doc_id,
            error=str(exc),
        )


def _process_document(
    file_path: str,
    file_ext: str,
    user_id: int,
    doc_id: str,
    doc_name: str,
    store: Any,
    settings: Settings,
) -> int:
    chunks = parse_document(
        file_path,
        file_ext,
        user_id=user_id,
        doc_id=doc_id,
        doc_name=doc_name,
        settings=settings,
    )
    return store.add_chunks(user_id, doc_id, doc_name, chunks)


async def ingest_document(
    doc_id: str,
    user_id: int,
    file_path: str,
    file_ext: str,
    doc_name: str,
    *,
    store: Any = None,
    settings: Optional[Settings] = None,
) -> bool:
    """执行单个文档的建库；返回是否最终进入 ready。"""
    settings = settings or get_settings()
    store = store or build_vector_store(settings)

    updated = await knowledge_document_repository.mark_processing(doc_id, user_id)
    if updated != 1:
        logger.info("knowledge_ingest_skipped", doc_id=doc_id, user_id=user_id)
        return False

    try:
        chunk_count = await run_in_threadpool(
            _process_document,
            file_path,
            file_ext,
            user_id,
            doc_id,
            doc_name,
            store,
            settings,
        )

        row = await knowledge_document_repository.get_document(doc_id, user_id)
        if row is None:
            _safe_delete_vectors(store, user_id, doc_id)
            logger.info("knowledge_ingest_document_deleted", doc_id=doc_id)
            return False

        ready = await knowledge_document_repository.mark_ready(
            doc_id, user_id, chunk_count
        )
        if ready != 1:
            _safe_delete_vectors(store, user_id, doc_id)
            logger.info("knowledge_ingest_ready_raced_deletion", doc_id=doc_id)
            return False
        logger.info(
            "knowledge_ingest_ready",
            doc_id=doc_id,
            user_id=user_id,
            chunks=chunk_count,
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "knowledge_ingest_failed", doc_id=doc_id, user_id=user_id, error=str(exc)
        )
        _safe_delete_vectors(store, user_id, doc_id)
        try:
            await knowledge_document_repository.mark_failed(
                doc_id, user_id, _readable_error(exc)
            )
        except Exception as mark_exc:  # noqa: BLE001
            logger.error(
                "knowledge_mark_failed_error", doc_id=doc_id, error=str(mark_exc)
            )
        return False


async def _run_ingestion(
    doc_id: str,
    user_id: int,
    file_path: str,
    file_ext: str,
    doc_name: str,
    settings: Settings,
    store: Any,
) -> None:
    async with _get_semaphore(settings):
        await ingest_document(
            doc_id,
            user_id,
            file_path,
            file_ext,
            doc_name,
            store=store,
            settings=settings,
        )


def schedule_ingestion(
    doc_id: str,
    user_id: int,
    file_path: str,
    file_ext: str,
    doc_name: str,
    *,
    settings: Optional[Settings] = None,
    store: Any = None,
) -> None:
    """创建后台建库任务；上传请求立即返回。"""
    settings = settings or get_settings()
    task = asyncio.create_task(
        _run_ingestion(
            doc_id,
            user_id,
            file_path,
            file_ext,
            doc_name,
            settings,
            store or build_vector_store(settings),
        )
    )
    _running_tasks.add(task)
    task.add_done_callback(_running_tasks.discard)


async def cleanup_on_startup(
    *, store: Any = None, settings: Optional[Settings] = None
) -> int:
    """启动清理：残留 pending/processing 文档置为 failed，并清理可能已写入的向量。"""
    settings = settings or get_settings()
    try:
        rows = await knowledge_document_repository.list_in_progress()
    except Exception as exc:  # noqa: BLE001
        logger.warning("knowledge_startup_list_failed", error=str(exc))
        rows = []

    try:
        count = await knowledge_document_repository.fail_in_progress(RESTART_ERROR)
    except Exception as exc:  # noqa: BLE001
        logger.warning("knowledge_startup_cleanup_failed", error=str(exc))
        return 0

    if rows:
        try:
            store = store or build_vector_store(settings)
        except Exception as exc:  # noqa: BLE001
            logger.warning("knowledge_startup_store_failed", error=str(exc))
            store = None
        if store is not None:
            for row in rows:
                _safe_delete_vectors(
                    store, int(row["user_id"]), str(row["doc_id"])
                )

    if count:
        logger.info("knowledge_startup_cleaned", count=count)
    return count
