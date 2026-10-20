"""个人知识库业务服务：概览、上传落盘、删除清理与文档范围校验。"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import UploadFile

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    DocumentProcessingError,
    KnowledgeBaseError,
    KnowledgeBaseUnavailableError,
    NotFoundError,
    ValidationError,
)
from app.core.logging import get_logger
from app.llm.document_parser import SUPPORTED_EXTENSIONS
from app.llm.knowledge_base import build_vector_store
from app.models.knowledge_document import (
    KnowledgeBaseOverview,
    KnowledgeBaseStats,
    KnowledgeDocumentOut,
)
from app.repositories import knowledge_document_repository
from app.services.knowledge_ingestion_service import schedule_ingestion
from app.utils.id_generator import generate_doc_id

logger = get_logger("knowledge_base_service")

MAX_DOCUMENTS_PER_SCOPE = 10
_ILLEGAL_FILE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_SUPPORTED_TEXT = "PDF、Word（.docx）、Markdown 与纯文本"


def _fmt_time(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value or "")


def _to_document(row: dict[str, Any]) -> KnowledgeDocumentOut:
    finished_at = row.get("finished_at")
    return KnowledgeDocumentOut(
        doc_id=str(row["doc_id"]),
        file_name=str(row.get("file_name") or ""),
        file_ext=str(row.get("file_ext") or ""),
        file_size=int(row.get("file_size") or 0),
        status=row.get("status") or "pending",
        chunk_count=int(row.get("chunk_count") or 0),
        error_message=row.get("error_message"),
        created_at=_fmt_time(row.get("created_at")),
        finished_at=_fmt_time(finished_at) if finished_at else None,
    )


async def get_overview(user_id: int) -> KnowledgeBaseOverview:
    stats = await knowledge_document_repository.get_stats(user_id)
    rows = await knowledge_document_repository.list_documents(user_id)
    return KnowledgeBaseOverview(
        stats=KnowledgeBaseStats(**stats),
        documents=[_to_document(row) for row in rows],
    )


def _sanitize_file_name(file_name: str) -> str:
    path = Path(file_name)
    stem = _ILLEGAL_FILE_CHARS.sub("_", path.stem).strip(" .") or "document"
    suffix = _ILLEGAL_FILE_CHARS.sub("", path.suffix)
    return (stem + suffix)[:200]


def _remove_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:  # noqa: BLE001
        logger.warning("knowledge_file_remove_failed", path=str(path), error=str(exc))


def _remove_empty_dirs(path: Path, stop: Path) -> None:
    root = stop.resolve()
    parent = path.parent
    while parent.resolve() != root and parent.resolve().is_relative_to(root):
        try:
            parent.rmdir()
        except OSError:
            return
        parent = parent.parent


def _delete_local_file(upload_root: Path, relative_path: str) -> None:
    if not relative_path:
        return
    try:
        root = upload_root.resolve()
        target = (root / relative_path).resolve()
    except OSError as exc:  # noqa: BLE001
        logger.warning("knowledge_file_resolve_failed", error=str(exc))
        return
    if not target.is_relative_to(root):
        logger.warning("knowledge_file_outside_root", path=str(target))
        return

    _remove_file(target)
    _remove_empty_dirs(target, upload_root)


async def upload_document(
    user_id: int,
    upload: UploadFile,
    *,
    file_name: Optional[str] = None,
    settings: Optional[Settings] = None,
) -> KnowledgeDocumentOut:
    settings = settings or get_settings()
    if not settings.knowledge_base_ready:
        raise KnowledgeBaseUnavailableError()

    # 微信小程序 uploadFile 只按临时路径命名，真实文件名需由表单字段单独传入
    original_name = Path(file_name or upload.filename or "").name
    if not original_name:
        raise ValidationError("文件名不能为空")
    display_name = _sanitize_file_name(original_name)
    file_ext = Path(display_name).suffix.lower().lstrip(".")
    if file_ext not in SUPPORTED_EXTENSIONS:
        raise ValidationError(f"不支持的文件格式，仅支持 {_SUPPORTED_TEXT}")

    doc_id = generate_doc_id()
    stored_name = display_name
    relative_path = f"{user_id}/{doc_id}/{stored_name}"
    target_dir = settings.kb_upload_path / str(user_id) / doc_id
    target_path = target_dir / stored_name

    total_bytes = 0
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        with target_path.open("wb") as handle:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > settings.kb_max_file_bytes:
                    raise ValidationError(
                        f"文件大小超过 {settings.kb_max_file_mb}MB 限制，请压缩或拆分后上传"
                    )
                handle.write(chunk)
        if total_bytes == 0:
            raise ValidationError("文件为空，请重新选择")
    except ValidationError:
        _remove_file(target_path)
        _remove_empty_dirs(target_path, settings.kb_upload_path)
        raise
    except Exception as exc:  # noqa: BLE001
        _remove_file(target_path)
        _remove_empty_dirs(target_path, settings.kb_upload_path)
        logger.error("knowledge_file_save_failed", user_id=user_id, error=str(exc))
        raise DocumentProcessingError("文档保存失败，请稍后重试") from exc
    finally:
        await upload.close()

    try:
        created = await knowledge_document_repository.create_document(
            doc_id=doc_id,
            user_id=user_id,
            file_name=display_name,
            file_ext=file_ext,
            file_size=total_bytes,
            file_path=relative_path,
        )
    except Exception as exc:  # noqa: BLE001
        _remove_file(target_path)
        _remove_empty_dirs(target_path, settings.kb_upload_path)
        logger.error("knowledge_document_create_failed", user_id=user_id, error=str(exc))
        raise DocumentProcessingError("文档保存失败，请稍后重试") from exc

    if created != 1:
        _remove_file(target_path)
        _remove_empty_dirs(target_path, settings.kb_upload_path)
        raise KnowledgeBaseError("文档保存失败，请稍后重试")

    logger.info(
        "knowledge_document_uploaded",
        user_id=user_id,
        doc_id=doc_id,
        file_name=display_name,
        file_ext=file_ext,
        file_size=total_bytes,
    )
    schedule_ingestion(
        doc_id,
        user_id,
        str(target_path),
        file_ext,
        display_name,
        settings=settings,
    )

    return KnowledgeDocumentOut(
        doc_id=doc_id,
        file_name=display_name,
        file_ext=file_ext,
        file_size=total_bytes,
        status="pending",
        chunk_count=0,
        created_at=_fmt_time(datetime.now()),
    )


async def delete_document(
    user_id: int,
    doc_id: str,
    *,
    store: Any = None,
    settings: Optional[Settings] = None,
) -> None:
    settings = settings or get_settings()
    row = await knowledge_document_repository.get_document(doc_id, user_id)
    if row is None:
        raise NotFoundError("文档不存在")

    store = store or build_vector_store(settings)
    try:
        store.delete_document(user_id, doc_id)
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "knowledge_vector_delete_failed",
            user_id=user_id,
            doc_id=doc_id,
            error=str(exc),
        )
        raise KnowledgeBaseError("文档删除失败，请稍后重试") from exc

    _delete_local_file(settings.kb_upload_path, str(row.get("file_path") or ""))

    try:
        rowcount = await knowledge_document_repository.delete_document(doc_id, user_id)
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "knowledge_document_delete_failed",
            user_id=user_id,
            doc_id=doc_id,
            error=str(exc),
        )
        raise KnowledgeBaseError("文档删除失败，请稍后重试") from exc

    if rowcount != 1:
        raise NotFoundError("文档不存在")


async def validate_document_scope(
    user_id: int,
    document_ids: list[str],
    *,
    settings: Optional[Settings] = None,
) -> list[str]:
    if not document_ids:
        return []
    settings = settings or get_settings()
    if not settings.knowledge_base_ready:
        raise KnowledgeBaseUnavailableError()

    unique_ids: list[str] = []
    seen: set[str] = set()
    for doc_id in document_ids:
        if doc_id in seen:
            continue
        seen.add(doc_id)
        row = await knowledge_document_repository.get_document(doc_id, user_id)
        if row is None:
            raise NotFoundError("文档不存在或无权访问")
        if row.get("status") != "ready":
            raise ValidationError("文档尚未就绪，请等待处理完成后再试")
        unique_ids.append(doc_id)

    if len(unique_ids) > MAX_DOCUMENTS_PER_SCOPE:
        raise ValidationError(f"单次最多选择 {MAX_DOCUMENTS_PER_SCOPE} 个文档")
    return unique_ids
