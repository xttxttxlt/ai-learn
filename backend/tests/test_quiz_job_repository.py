from app.repositories import quiz_job_repository as repo
from tests.fake_db import FakeDB


async def test_create_job_uses_duplicate_key_idempotency(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.execute_queue = [(1, 1)]

    rowcount = await repo.create_job("job_a", 7, "req_1", {"user_input": "RAG"})

    assert rowcount == 1
    sql, args = fake.executed[0]
    assert "ON DUPLICATE KEY UPDATE" in sql
    assert args[:3] == ("job_a", 7, "req_1")
    assert '"user_input": "RAG"' in args[3]


async def test_get_job_filters_by_owner(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.fetch_one_queue = [{"job_id": "job_a", "status": "running"}]

    row = await repo.get_job("job_a", 7)

    assert row["status"] == "running"
    sql, args = fake.fetch_one_calls[0]
    assert "WHERE job_id = %s AND user_id = %s" in sql
    assert args == ("job_a", 7)


async def test_get_by_request_filters_by_owner(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.fetch_one_queue = [{"job_id": "job_a", "status": "pending"}]

    row = await repo.get_by_request(7, "req_1")

    assert row["job_id"] == "job_a"
    sql, args = fake.fetch_one_calls[0]
    assert "WHERE user_id = %s AND request_id = %s" in sql
    assert args == (7, "req_1")


async def test_mark_running_only_from_pending(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.execute_queue = [(0, 1)]

    assert await repo.mark_running("job_a", 7) == 1

    sql, args = fake.executed[0]
    assert "status = 'running'" in sql
    assert "AND status = 'pending'" in sql
    assert args == ("job_a", 7)


async def test_mark_completed_writes_result_and_finished_at(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.execute_queue = [(0, 1)]

    await repo.mark_completed("job_a", 7, {"quiz_id": "quiz_a"})

    sql, args = fake.executed[0]
    assert "result_json = %s" in sql
    assert "timings_json = %s" in sql
    assert "finished_at = NOW()" in sql
    assert args[0] == '{"quiz_id": "quiz_a"}'
    assert args[1] is None
    assert args[2:] == ("job_a", 7)


async def test_mark_failed_truncates_message(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.execute_queue = [(0, 1)]

    await repo.mark_failed("job_a", 7, "x" * 600)

    assert len(fake.executed[0][1][0]) == 500


async def test_fail_if_timed_out_is_conditional(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.execute_queue = [(0, 1)]

    assert await repo.fail_if_timed_out("job_a", 7, 300) == 1

    sql, args = fake.executed[0]
    assert "DATE_SUB(NOW(), INTERVAL %s SECOND)" in sql
    assert "status = 'running'" in sql
    assert args == ("生成超时，请重试", "job_a", 7, 300)


async def test_fail_in_progress_sweeps_pending_and_running(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.execute_queue = [(0, 2)]

    assert await repo.fail_in_progress("服务重启，任务已中断") == 2

    sql, args = fake.executed[0]
    assert "status IN ('pending', 'running')" in sql
    assert args == ("服务重启，任务已中断",)
