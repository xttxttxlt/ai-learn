from datetime import datetime

import pytest

from app.core.config import Settings
from app.core.exceptions import (
    KnowledgeBaseError,
    KnowledgeBaseUnavailableError,
    NotFoundError,
    ValidationError,
)
from app.services import knowledge_base_service as service
from tests.fake_db import FakeDB


def _settings(tmp_path, **kwargs):
    values = {
        "dashscope_api_key": "test-key",
        "kb_upload_dir": str(tmp_path / "upload"),
        "chroma_persist_dir": str(tmp_path / "chroma"),
    }
    values.update(kwargs)
    return Settings(_env_file=None, **values)


def _doc_row(**kwargs):
    row = {
        "doc_id": "doc_1",
        "user_id": 7,
        "file_name": "笔记.md",
        "file_ext": "md",
        "file_size": 1024,
        "file_path": "7/doc_1/笔记.md",
        "status": "ready",
        "chunk_count": 17,
        "error_message": None,
        "created_at": datetime(2026, 10, 20, 10, 0, 0),
        "finished_at": None,
    }
    row.update(kwargs)
    return row


class FakeStore:
    def __init__(self, error=None):
        self.deleted: list[tuple] = []
        self.error = error

    def delete_document(self, user_id, doc_id):
        if self.error:
            raise self.error
        self.deleted.append((user_id, doc_id))


async def test_get_overview_returns_stats_and_documents(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.fetch_one_queue = [
        {
            "total_documents": 3,
            "ready_documents": 1,
            "processing_documents": 1,
            "failed_documents": 1,
            "total_chunks": 17,
        }
    ]
    fake.fetch_all_queue = [[_doc_row()]]

    overview = await service.get_overview(7)

    assert overview.stats.total_documents == 3
    assert overview.stats.ready_documents == 1
    assert overview.stats.processing_documents == 1
    assert overview.stats.failed_documents == 1
    assert overview.stats.total_chunks == 17
    assert len(overview.documents) == 1
    document = overview.documents[0]
    assert document.doc_id == "doc_1"
    assert document.file_name == "笔记.md"
    assert document.chunk_count == 17
    assert document.created_at == "2026-10-20 10:00:00"


async def test_delete_document_cleans_vectors_file_and_row(monkeypatch, tmp_path):
    fake = FakeDB().install(monkeypatch)
    fake.fetch_one_queue = [_doc_row()]
    fake.execute_queue = [(0, 1)]
    settings = _settings(tmp_path)
    file_path = settings.kb_upload_path / "7" / "doc_1" / "笔记.md"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("内容", encoding="utf-8")
    store = FakeStore()

    await service.delete_document(7, "doc_1", store=store, settings=settings)

    assert store.deleted == [(7, "doc_1")]
    assert not file_path.exists()
    sql, args = fake.executed[0]
    assert sql.startswith("DELETE FROM knowledge_documents")
    assert args == ("doc_1", 7)


async def test_delete_document_missing_file_still_deletes_row(monkeypatch, tmp_path):
    fake = FakeDB().install(monkeypatch)
    fake.fetch_one_queue = [_doc_row()]
    fake.execute_queue = [(0, 1)]
    settings = _settings(tmp_path)

    await service.delete_document(7, "doc_1", store=FakeStore(), settings=settings)

    assert fake.executed


async def test_delete_document_not_found(monkeypatch, tmp_path):
    FakeDB().install(monkeypatch)

    with pytest.raises(NotFoundError):
        await service.delete_document(
            7, "doc_missing", store=FakeStore(), settings=_settings(tmp_path)
        )


async def test_delete_document_aborts_when_vector_cleanup_fails(monkeypatch, tmp_path):
    fake = FakeDB().install(monkeypatch)
    fake.fetch_one_queue = [_doc_row()]
    settings = _settings(tmp_path)
    file_path = settings.kb_upload_path / "7" / "doc_1" / "笔记.md"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("内容", encoding="utf-8")

    with pytest.raises(KnowledgeBaseError) as excinfo:
        await service.delete_document(
            7, "doc_1", store=FakeStore(error=RuntimeError("chroma down")), settings=settings
        )

    assert excinfo.value.code == 4005
    assert file_path.exists()
    assert fake.executed == []


async def test_delete_document_refuses_path_outside_upload_root(monkeypatch, tmp_path):
    fake = FakeDB().install(monkeypatch)
    outside = tmp_path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    fake.fetch_one_queue = [_doc_row(file_path="../secret.txt")]
    fake.execute_queue = [(0, 1)]
    settings = _settings(tmp_path)

    await service.delete_document(7, "doc_1", store=FakeStore(), settings=settings)

    assert outside.exists()
    assert fake.executed


async def test_validate_scope_accepts_ready_documents(monkeypatch, tmp_path):
    fake = FakeDB().install(monkeypatch)
    fake.fetch_one_queue = [_doc_row(), _doc_row(doc_id="doc_2")]

    ids = await service.validate_document_scope(
        7, ["doc_1", "doc_2", "doc_1"], settings=_settings(tmp_path)
    )

    assert ids == ["doc_1", "doc_2"]
    assert len(fake.fetch_one_calls) == 2
    for _, args in fake.fetch_one_calls:
        assert args[1] == 7


async def test_validate_scope_missing_document_raises_not_found(monkeypatch, tmp_path):
    FakeDB().install(monkeypatch)

    with pytest.raises(NotFoundError):
        await service.validate_document_scope(
            7, ["doc_missing"], settings=_settings(tmp_path)
        )


async def test_validate_scope_not_ready_raises_validation(monkeypatch, tmp_path):
    fake = FakeDB().install(monkeypatch)
    fake.fetch_one_queue = [_doc_row(status="processing")]

    with pytest.raises(ValidationError) as excinfo:
        await service.validate_document_scope(
            7, ["doc_1"], settings=_settings(tmp_path)
        )

    assert "尚未就绪" in excinfo.value.message


async def test_validate_scope_requires_knowledge_base_config(monkeypatch, tmp_path):
    FakeDB().install(monkeypatch)

    with pytest.raises(KnowledgeBaseUnavailableError) as excinfo:
        await service.validate_document_scope(
            7, ["doc_1"], settings=_settings(tmp_path, dashscope_api_key="")
        )

    assert excinfo.value.code == 4007


async def test_validate_scope_empty_skips_checks(monkeypatch, tmp_path):
    FakeDB().install(monkeypatch)

    ids = await service.validate_document_scope(
        7, [], settings=_settings(tmp_path, dashscope_api_key="")
    )

    assert ids == []
