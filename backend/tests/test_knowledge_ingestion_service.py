import asyncio

import pytest

from app.core.config import Settings
from app.llm.document_parser import DocumentChunk, DocumentParseError
from app.llm.knowledge_base import EmbeddingServiceError
from app.services import knowledge_ingestion_service as service
from tests.fake_db import FakeDB


def _settings(**kwargs):
    return Settings(_env_file=None, dashscope_api_key="test-key", **kwargs)


def _chunks(n=2):
    return [
        DocumentChunk(text=f"内容 {i}", metadata={"chunk_index": i})
        for i in range(n)
    ]


class FakeStore:
    def __init__(self, add_error=None):
        self.added: list[tuple] = []
        self.deleted: list[tuple] = []
        self.add_error = add_error

    def add_chunks(self, user_id, doc_id, doc_name, chunks):
        self.added.append((user_id, doc_id, doc_name, len(chunks)))
        if self.add_error:
            raise self.add_error
        return len(chunks)

    def delete_document(self, user_id, doc_id):
        self.deleted.append((user_id, doc_id))


@pytest.fixture(autouse=True)
def _reset_state():
    service._ingestion_semaphore = None
    service._running_tasks.clear()
    yield
    service._ingestion_semaphore = None
    service._running_tasks.clear()


async def _run(monkeypatch, fake, store, chunks=None):
    fake.install(monkeypatch)
    if chunks is not None:
        monkeypatch.setattr(service, "parse_document", lambda *a, **kw: chunks)
    return await service.ingest_document(
        "doc_1",
        7,
        "C:/tmp/a.md",
        "md",
        "笔记.md",
        store=store,
        settings=_settings(),
    )


async def test_ingest_success_marks_ready(monkeypatch):
    fake = FakeDB()
    fake.execute_queue = [(0, 1), (0, 1)]
    fake.fetch_one_queue = [{"doc_id": "doc_1", "user_id": 7}]
    store = FakeStore()

    result = await _run(monkeypatch, fake, store, chunks=_chunks(2))

    assert result is True
    assert store.added == [(7, "doc_1", "笔记.md", 2)]
    assert "status = 'processing'" in fake.executed[0][0]
    assert "status = 'ready'" in fake.executed[1][0]
    assert fake.executed[1][1] == (2, "doc_1", 7)


async def test_ingest_parse_failure_marks_failed_and_cleans_vectors(monkeypatch):
    fake = FakeDB()
    fake.execute_queue = [(0, 1), (0, 1)]
    store = FakeStore()

    def boom(*args, **kwargs):
        raise DocumentParseError("未提取到可用文本，请确认文档内容不是空白或扫描件")

    fake.install(monkeypatch)
    monkeypatch.setattr(service, "parse_document", boom)

    result = await service.ingest_document(
        "doc_1", 7, "C:/tmp/a.md", "md", "笔记.md", store=store, settings=_settings()
    )

    assert result is False
    assert store.deleted == [(7, "doc_1")]
    assert "status = 'failed'" in fake.executed[1][0]
    assert fake.executed[1][1][0] == "未提取到可用文本，请确认文档内容不是空白或扫描件"


async def test_ingest_embedding_failure_marks_failed_with_readable_message(monkeypatch):
    fake = FakeDB()
    fake.execute_queue = [(0, 1), (0, 1)]
    fake.fetch_one_queue = []
    store = FakeStore(add_error=EmbeddingServiceError("Embedding 维度不一致（期望 1024，实际 2）"))

    result = await _run(monkeypatch, fake, store, chunks=_chunks(1))

    assert result is False
    assert "status = 'failed'" in fake.executed[1][0]
    assert "维度不一致" in fake.executed[1][1][0]
    assert store.deleted == [(7, "doc_1")]


async def test_ingest_unexpected_error_hides_internal_detail(monkeypatch):
    fake = FakeDB()
    fake.execute_queue = [(0, 1), (0, 1)]
    store = FakeStore()

    def boom(*args, **kwargs):
        raise RuntimeError("secret-internal-stack")

    fake.install(monkeypatch)
    monkeypatch.setattr(service, "parse_document", boom)

    result = await service.ingest_document(
        "doc_1", 7, "C:/tmp/a.md", "md", "笔记.md", store=store, settings=_settings()
    )

    assert result is False
    message = fake.executed[1][1][0]
    assert message == "文档处理失败，请稍后重试"
    assert "secret" not in message


async def test_ingest_aborts_when_document_already_deleted(monkeypatch):
    fake = FakeDB()
    fake.execute_queue = [(0, 0)]
    store = FakeStore()
    called: list[bool] = []

    def parser(*args, **kwargs):
        called.append(True)
        return _chunks(1)

    fake.install(monkeypatch)
    monkeypatch.setattr(service, "parse_document", parser)

    result = await service.ingest_document(
        "doc_1", 7, "C:/tmp/a.md", "md", "笔记.md", store=store, settings=_settings()
    )

    assert result is False
    assert called == []
    assert store.added == []


async def test_ingest_discards_vectors_if_document_deleted_during_processing(monkeypatch):
    fake = FakeDB()
    fake.execute_queue = [(0, 1)]
    fake.fetch_one_queue = [None]
    store = FakeStore()

    result = await _run(monkeypatch, fake, store, chunks=_chunks(2))

    assert result is False
    assert store.added == [(7, "doc_1", "笔记.md", 2)]
    assert store.deleted == [(7, "doc_1")]
    assert all("status = 'ready'" not in sql for sql, _ in fake.executed)


async def test_ingest_discards_vectors_if_ready_update_races_deletion(monkeypatch):
    fake = FakeDB()
    fake.execute_queue = [(0, 1), (0, 0)]
    fake.fetch_one_queue = [{"doc_id": "doc_1", "user_id": 7}]
    store = FakeStore()

    result = await _run(monkeypatch, fake, store, chunks=_chunks(1))

    assert result is False
    assert store.deleted == [(7, "doc_1")]


async def test_schedule_ingestion_runs_in_background(monkeypatch):
    called = asyncio.Event()
    captured: list[tuple] = []

    async def fake_ingest(*args, **kwargs):
        captured.append(args)
        called.set()

    monkeypatch.setattr(service, "ingest_document", fake_ingest)

    service.schedule_ingestion(
        "doc_1", 7, "C:/tmp/a.md", "md", "笔记.md", settings=_settings()
    )
    await asyncio.wait_for(called.wait(), timeout=1)

    assert captured and captured[0][0] == "doc_1"


async def test_cleanup_on_startup_marks_failed_and_cleans_vectors(monkeypatch):
    fake = FakeDB()
    fake.fetch_all_queue = [[{"doc_id": "doc_1", "user_id": 7}]]
    fake.execute_queue = [(0, 2)]
    fake.install(monkeypatch)
    store = FakeStore()

    count = await service.cleanup_on_startup(store=store, settings=_settings())

    assert count == 2
    assert store.deleted == [(7, "doc_1")]
    sql, args = fake.executed[0]
    assert "status IN ('pending', 'processing')" in sql
    assert args == ("服务重启，处理已中断，请重新上传",)


async def test_cleanup_on_startup_swallows_db_error(monkeypatch):
    fake = FakeDB()
    fake.install(monkeypatch)

    async def boom(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(service.knowledge_document_repository, "fail_in_progress", boom)

    count = await service.cleanup_on_startup(store=FakeStore(), settings=_settings())

    assert count == 0


async def test_cleanup_on_startup_still_marks_failed_when_listing_fails(monkeypatch):
    fake = FakeDB()
    fake.execute_queue = [(0, 1)]
    fake.install(monkeypatch)

    async def boom(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(service.knowledge_document_repository, "list_in_progress", boom)

    count = await service.cleanup_on_startup(store=FakeStore(), settings=_settings())

    assert count == 1


async def test_lifespan_calls_knowledge_cleanup(monkeypatch):
    import app.main as main

    calls: list[str] = []

    async def fake_init():
        calls.append("init")

    async def fake_quiz_cleanup():
        calls.append("quiz")

    async def fake_kb_cleanup():
        calls.append("kb")

    async def fake_close():
        calls.append("close")

    monkeypatch.setattr(main, "init_db", fake_init)
    monkeypatch.setattr(main, "close_db", fake_close)
    monkeypatch.setattr(main.quiz_job_service, "cleanup_on_startup", fake_quiz_cleanup)
    monkeypatch.setattr(
        main.knowledge_ingestion_service, "cleanup_on_startup", fake_kb_cleanup
    )

    async with main.lifespan(main.app):
        pass

    assert calls == ["init", "quiz", "kb", "close"]
