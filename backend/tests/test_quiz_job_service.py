import json

import pytest

from app.core.exceptions import (
    ContentFilteredError,
    NotFoundError,
    QuizGenerationError,
    ServiceUnavailableError,
    ValidationError,
)
from app.models.quiz import Option, Question, Quiz, QuizGenerateRequest
from app.models.quiz_job import QuizJobCreateRequest
from app.services import quiz_job_service
from app.services.quiz_job_service import _run_job
from tests.fake_db import FakeDB


def _quiz(quiz_id="quiz_test"):
    return Quiz(
        quiz_id=quiz_id,
        title="RAG 入门",
        summary="基础题",
        user_input="什么是 RAG",
        questions=[
            Question(
                id="q1",
                type="single",
                stem="RAG 是什么？",
                options=[Option(key="A", text="检索增强生成"), Option(key="B", text="数据库")],
                answer=["A"],
                explanation="RAG=检索增强生成",
                knowledge_point="RAG 定义",
                difficulty="easy",
            )
        ],
    )


def _row(status, **extra):
    row = {
        "job_id": "job_a",
        "user_id": 7,
        "status": status,
        "result_json": None,
        "error_message": None,
    }
    row.update(extra)
    return row


@pytest.fixture(autouse=True)
def _reset_runner():
    quiz_job_service._job_semaphore = None
    quiz_job_service._running_tasks.clear()
    yield
    quiz_job_service._job_semaphore = None
    quiz_job_service._running_tasks.clear()


async def test_create_job_new_submits_background_task(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.execute_queue = [(1, 1)]
    fake.fetch_one_queue = [_row("pending", job_id="job_new")]
    monkeypatch.setattr(quiz_job_service, "generate_job_id", lambda: "job_new")
    submitted: list[tuple] = []
    monkeypatch.setattr(quiz_job_service, "_submit", lambda *args: submitted.append(args))

    created = await quiz_job_service.create_job(
        7, QuizJobCreateRequest(user_input="  什么是 RAG  ", request_id="req_1")
    )

    assert created.job_id == "job_new"
    assert created.status == "pending"
    assert len(submitted) == 1
    assert submitted[0][0] == "job_new"
    assert submitted[0][2].user_input == "什么是 RAG"
    _, args = fake.executed[0]
    assert '"user_input": "什么是 RAG"' in args[3]


async def test_create_job_persists_explicit_source_flags(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.execute_queue = [(1, 1)]
    fake.fetch_one_queue = [_row("pending", job_id="job_new")]
    monkeypatch.setattr(quiz_job_service, "generate_job_id", lambda: "job_new")
    submitted: list[tuple] = []
    monkeypatch.setattr(quiz_job_service, "_submit", lambda *args: submitted.append(args))

    await quiz_job_service.create_job(
        7,
        QuizJobCreateRequest(user_input="RAG", request_id="req_web", use_web_search=True),
    )

    params = json.loads(fake.executed[0][1][3])
    assert params["use_web_search"] is True
    assert params["use_knowledge_base"] is False
    assert params["generate_images"] is False
    assert "document_id" not in params
    assert submitted[0][2].use_web_search is True
    assert submitted[0][2].use_knowledge_base is False


async def test_create_job_duplicate_request_returns_existing_without_submitting(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.execute_queue = [(0, 0)]
    fake.fetch_one_queue = [_row("running", job_id="job_existing")]
    monkeypatch.setattr(quiz_job_service, "generate_job_id", lambda: "job_attempt")
    submitted: list[tuple] = []
    monkeypatch.setattr(quiz_job_service, "_submit", lambda *args: submitted.append(args))

    created = await quiz_job_service.create_job(
        7, QuizJobCreateRequest(user_input="RAG", request_id="req_1")
    )

    assert created.job_id == "job_existing"
    assert created.status == "running"
    assert submitted == []


async def test_create_job_rejects_blank_input_after_clean():
    with pytest.raises(ValidationError):
        await quiz_job_service.create_job(
            7, QuizJobCreateRequest(user_input="   ", request_id="req_1")
        )


async def test_create_job_rejects_sensitive_input():
    with pytest.raises(ContentFilteredError):
        await quiz_job_service.create_job(
            7, QuizJobCreateRequest(user_input="赌博技巧", request_id="req_1")
        )


async def test_create_job_db_failure_maps_to_service_unavailable(monkeypatch):
    FakeDB().install(monkeypatch)

    async def boom(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(quiz_job_service.quiz_job_repository, "create_job", boom)

    with pytest.raises(ServiceUnavailableError):
        await quiz_job_service.create_job(
            7, QuizJobCreateRequest(user_input="RAG", request_id="req_1")
        )


async def test_run_job_completes_and_writes_result(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.execute_queue = [(0, 1), (0, 1)]
    quiz = _quiz()
    persisted: list[tuple] = []
    monkeypatch.setattr(quiz_job_service, "generate_quiz", lambda req, **kwargs: quiz)

    async def fake_persist(user_id, q):
        persisted.append((user_id, q.quiz_id))

    monkeypatch.setattr(quiz_job_service.persistence_service, "persist_quiz", fake_persist)

    await _run_job("job_a", 7, QuizGenerateRequest(user_input="RAG"))

    assert persisted == [(7, "quiz_test")]
    assert "status = 'running'" in fake.executed[0][0]
    sql, args = fake.executed[1]
    assert "status = 'completed'" in sql
    assert '"quiz_id": "quiz_test"' in args[0]


async def test_run_job_marks_failed_with_readable_message(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.execute_queue = [(0, 1), (0, 1)]

    def boom(req, **kwargs):
        raise QuizGenerationError()

    monkeypatch.setattr(quiz_job_service, "generate_quiz", boom)

    await _run_job("job_a", 7, QuizGenerateRequest(user_input="RAG"))

    sql, args = fake.executed[1]
    assert "status = 'failed'" in sql
    assert args[0] == "题库生成失败，请稍后重试"


async def test_run_job_completes_even_if_persist_raises(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.execute_queue = [(0, 1), (0, 1)]
    monkeypatch.setattr(quiz_job_service, "generate_quiz", lambda req, **kwargs: _quiz())

    async def boom_persist(user_id, quiz):
        raise RuntimeError("db down")

    monkeypatch.setattr(quiz_job_service.persistence_service, "persist_quiz", boom_persist)

    await _run_job("job_a", 7, QuizGenerateRequest(user_input="RAG"))

    assert "status = 'completed'" in fake.executed[1][0]


async def test_get_job_not_found(monkeypatch):
    FakeDB().install(monkeypatch)

    with pytest.raises(NotFoundError):
        await quiz_job_service.get_job(7, "job_missing")


async def test_get_job_running_checks_timeout_without_result(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.fetch_one_queue = [_row("running")]
    fake.execute_queue = [(0, 0)]

    job = await quiz_job_service.get_job(7, "job_a")

    assert job.status == "running"
    assert job.quiz is None
    assert job.error is None
    assert "INTERVAL %s SECOND" in fake.executed[0][0]


async def test_get_job_marks_timed_out_running_as_failed(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.fetch_one_queue = [
        _row("running"),
        _row("failed", error_message="生成超时，请重试"),
    ]
    fake.execute_queue = [(0, 1)]

    job = await quiz_job_service.get_job(7, "job_a")

    assert job.status == "failed"
    assert job.error == "生成超时，请重试"


async def test_get_job_completed_parses_result_json_string(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.fetch_one_queue = [
        _row("completed", result_json=json.dumps(_quiz().model_dump(), ensure_ascii=False))
    ]

    job = await quiz_job_service.get_job(7, "job_a")

    assert job.status == "completed"
    assert job.quiz is not None
    assert job.quiz.quiz_id == "quiz_test"
    assert job.error is None


async def test_get_job_failed_returns_error_message(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.fetch_one_queue = [_row("failed", error_message="题库生成失败，请稍后重试")]

    job = await quiz_job_service.get_job(7, "job_a")

    assert job.status == "failed"
    assert job.error == "题库生成失败，请稍后重试"
    assert job.quiz is None


async def test_cleanup_on_startup_fails_in_progress_jobs(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.execute_queue = [(0, 3)]

    await quiz_job_service.cleanup_on_startup()

    sql, args = fake.executed[0]
    assert "status IN ('pending', 'running')" in sql
    assert args == ("服务重启，任务已中断，请重新生成",)


async def test_cleanup_on_startup_swallows_db_error(monkeypatch):
    FakeDB().install(monkeypatch)

    async def boom(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(quiz_job_service.quiz_job_repository, "fail_in_progress", boom)

    await quiz_job_service.cleanup_on_startup()
