from app.repositories import knowledge_document_repository as repo
from tests.fake_db import FakeDB


async def test_create_document_inserts_pending_row(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.execute_queue = [(1, 1)]

    rowcount = await repo.create_document(
        doc_id="doc_1",
        user_id=7,
        file_name="笔记.md",
        file_ext="md",
        file_size=1024,
        file_path="data/knowledge_base/7/doc_1/笔记.md",
    )

    assert rowcount == 1
    sql, args = fake.executed[0]
    assert "INSERT INTO knowledge_documents" in sql
    assert "'pending'" in sql
    assert args == (
        "doc_1",
        7,
        "笔记.md",
        "md",
        1024,
        "data/knowledge_base/7/doc_1/笔记.md",
    )


async def test_get_document_is_user_scoped(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.fetch_one_queue = [{"doc_id": "doc_1", "user_id": 7}]

    row = await repo.get_document("doc_1", 7)

    assert row["doc_id"] == "doc_1"
    sql, args = fake.fetch_one_calls[0]
    assert "doc_id = %s" in sql
    assert "user_id = %s" in sql
    assert args == ("doc_1", 7)


async def test_list_documents_is_user_scoped_and_ordered(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.fetch_all_queue = [[{"doc_id": "doc_1"}]]

    rows = await repo.list_documents(7)

    assert rows == [{"doc_id": "doc_1"}]
    sql, args = fake.fetch_all_calls[0]
    assert "WHERE user_id = %s" in sql
    assert "ORDER BY created_at DESC" in sql
    assert args == (7,)


async def test_list_documents_page_applies_limit_and_offset(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.fetch_all_queue = [[{"doc_id": "doc_11"}]]

    rows = await repo.list_documents_page(7, offset=10, limit=10)

    assert rows == [{"doc_id": "doc_11"}]
    sql, args = fake.fetch_all_calls[0]
    assert "WHERE user_id = %s" in sql
    assert "ORDER BY created_at DESC" in sql
    assert "LIMIT %s OFFSET %s" in sql
    assert args == (7, 10, 10)


async def test_count_documents_is_user_scoped(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.fetch_one_queue = [{"total": 12}]

    total = await repo.count_documents(7)

    assert total == 12
    sql, args = fake.fetch_one_calls[0]
    assert "COUNT(*)" in sql
    assert "WHERE user_id = %s" in sql
    assert args == (7,)


async def test_get_stats_aggregates_and_normalizes(monkeypatch):
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

    stats = await repo.get_stats(7)

    assert stats == {
        "total_documents": 3,
        "ready_documents": 1,
        "processing_documents": 1,
        "failed_documents": 1,
        "total_chunks": 17,
    }
    sql, args = fake.fetch_one_calls[0]
    assert "FROM knowledge_documents WHERE user_id = %s" in sql
    assert args == (7,)


async def test_get_stats_defaults_to_zero(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.fetch_one_queue = [None]

    stats = await repo.get_stats(7)

    assert stats == {
        "total_documents": 0,
        "ready_documents": 0,
        "processing_documents": 0,
        "failed_documents": 0,
        "total_chunks": 0,
    }


async def test_mark_processing_only_from_pending(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.execute_queue = [(0, 1)]

    rowcount = await repo.mark_processing("doc_1", 7)

    assert rowcount == 1
    sql, args = fake.executed[0]
    assert "SET status = 'processing'" in sql
    assert "status = 'pending'" in sql
    assert "user_id = %s" in sql
    assert args == ("doc_1", 7)


async def test_mark_ready_sets_chunk_count_and_finished_at(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.execute_queue = [(0, 1)]

    rowcount = await repo.mark_ready("doc_1", 7, 17)

    assert rowcount == 1
    sql, args = fake.executed[0]
    assert "SET status = 'ready'" in sql
    assert "chunk_count = %s" in sql
    assert "finished_at = NOW()" in sql
    assert "status IN ('pending', 'processing')" in sql
    assert args == (17, "doc_1", 7)


async def test_mark_failed_truncates_error_and_sets_finished_at(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.execute_queue = [(0, 1)]

    rowcount = await repo.mark_failed("doc_1", 7, "x" * 800)

    assert rowcount == 1
    sql, args = fake.executed[0]
    assert "SET status = 'failed'" in sql
    assert "error_message = %s" in sql
    assert "finished_at = NOW()" in sql
    assert args[1:] == ("doc_1", 7)
    assert len(args[0]) == 500


async def test_delete_document_is_user_scoped(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.execute_queue = [(0, 1)]

    rowcount = await repo.delete_document("doc_1", 7)

    assert rowcount == 1
    sql, args = fake.executed[0]
    assert sql.startswith("DELETE FROM knowledge_documents")
    assert "doc_id = %s AND user_id = %s" in sql
    assert args == ("doc_1", 7)


async def test_fail_in_progress_only_touches_pending_and_processing(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.execute_queue = [(0, 2)]

    rowcount = await repo.fail_in_progress("服务重启，处理已中断，请重新上传")

    assert rowcount == 2
    sql, args = fake.executed[0]
    assert "status IN ('pending', 'processing')" in sql
    assert "finished_at = NOW()" in sql
    assert args == ("服务重启，处理已中断，请重新上传",)


async def test_count_ready_returns_zero_when_missing(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.fetch_one_queue = [None]

    assert await repo.count_ready(7) == 0
    sql, args = fake.fetch_one_calls[0]
    assert "status = 'ready'" in sql
    assert "user_id = %s" in sql
    assert args == (7,)


async def test_count_ready_returns_number(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.fetch_one_queue = [{"ready_count": 2}]

    assert await repo.count_ready(7) == 2


async def test_list_in_progress_returns_doc_and_user(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.fetch_all_queue = [[{"doc_id": "doc_1", "user_id": 7}]]

    rows = await repo.list_in_progress()

    assert rows == [{"doc_id": "doc_1", "user_id": 7}]
    sql, _ = fake.fetch_all_calls[0]
    assert "status IN ('pending', 'processing')" in sql
