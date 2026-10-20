"""knowledge_documents 表的创建、查询、状态流转与清理。"""

from typing import Any, Optional

from app.core import db


async def create_document(
    doc_id: str,
    user_id: int,
    file_name: str,
    file_ext: str,
    file_size: int,
    file_path: str,
) -> int:
    _, rowcount = await db.execute(
        """INSERT INTO knowledge_documents
           (doc_id, user_id, file_name, file_ext, file_size, file_path, status)
           VALUES (%s, %s, %s, %s, %s, %s, 'pending')""",
        (doc_id, user_id, file_name, file_ext, file_size, file_path),
    )
    return rowcount


async def get_document(doc_id: str, user_id: int) -> Optional[dict[str, Any]]:
    return await db.fetch_one(
        "SELECT * FROM knowledge_documents WHERE doc_id = %s AND user_id = %s",
        (doc_id, user_id),
    )


async def list_documents(user_id: int) -> list[dict[str, Any]]:
    return await db.fetch_all(
        """SELECT * FROM knowledge_documents
           WHERE user_id = %s ORDER BY created_at DESC, id DESC""",
        (user_id,),
    )


async def get_stats(user_id: int) -> dict[str, int]:
    row = await db.fetch_one(
        """SELECT COUNT(*) AS total_documents,
                  COALESCE(SUM(status = 'ready'), 0) AS ready_documents,
                  COALESCE(SUM(status IN ('pending', 'processing')), 0) AS processing_documents,
                  COALESCE(SUM(status = 'failed'), 0) AS failed_documents,
                  COALESCE(SUM(CASE WHEN status = 'ready' THEN chunk_count ELSE 0 END), 0)
                      AS total_chunks
           FROM knowledge_documents WHERE user_id = %s""",
        (user_id,),
    )
    row = row or {}
    return {
        "total_documents": int(row.get("total_documents") or 0),
        "ready_documents": int(row.get("ready_documents") or 0),
        "processing_documents": int(row.get("processing_documents") or 0),
        "failed_documents": int(row.get("failed_documents") or 0),
        "total_chunks": int(row.get("total_chunks") or 0),
    }


async def count_ready(user_id: int) -> int:
    row = await db.fetch_one(
        """SELECT COUNT(*) AS ready_count FROM knowledge_documents
           WHERE user_id = %s AND status = 'ready'""",
        (user_id,),
    )
    return int((row or {}).get("ready_count") or 0)


async def list_in_progress() -> list[dict[str, Any]]:
    return await db.fetch_all(
        """SELECT doc_id, user_id FROM knowledge_documents
           WHERE status IN ('pending', 'processing')"""
    )


async def mark_processing(doc_id: str, user_id: int) -> int:
    _, rowcount = await db.execute(
        """UPDATE knowledge_documents SET status = 'processing'
           WHERE doc_id = %s AND user_id = %s AND status = 'pending'""",
        (doc_id, user_id),
    )
    return rowcount


async def mark_ready(doc_id: str, user_id: int, chunk_count: int) -> int:
    _, rowcount = await db.execute(
        """UPDATE knowledge_documents
           SET status = 'ready', chunk_count = %s, error_message = NULL,
               finished_at = NOW()
           WHERE doc_id = %s AND user_id = %s
             AND status IN ('pending', 'processing')""",
        (chunk_count, doc_id, user_id),
    )
    return rowcount


async def mark_failed(doc_id: str, user_id: int, error_message: str) -> int:
    _, rowcount = await db.execute(
        """UPDATE knowledge_documents
           SET status = 'failed', error_message = %s, finished_at = NOW()
           WHERE doc_id = %s AND user_id = %s
             AND status IN ('pending', 'processing')""",
        (error_message[:500], doc_id, user_id),
    )
    return rowcount


async def delete_document(doc_id: str, user_id: int) -> int:
    _, rowcount = await db.execute(
        "DELETE FROM knowledge_documents WHERE doc_id = %s AND user_id = %s",
        (doc_id, user_id),
    )
    return rowcount


async def fail_in_progress(error_message: str) -> int:
    """启动清理：把残留的 pending / processing 文档统一置为 failed。"""
    _, rowcount = await db.execute(
        """UPDATE knowledge_documents
           SET status = 'failed', error_message = %s, finished_at = NOW()
           WHERE status IN ('pending', 'processing')""",
        (error_message[:500],),
    )
    return rowcount
