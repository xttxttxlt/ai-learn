import json

import pytest
from fastapi.testclient import TestClient

from app.core.auth import create_token
from app.core.exceptions import QuizGenerationError, ValidationError
from app.llm.knowledge_base import KnowledgeScope
from app.main import app
from app.models.quiz import Option, Question, Quiz, QuizGenerateRequest
from app.models.quiz_job import QuizJobCreateRequest, QuizJobCreated
from app.services import quiz_job_service
from app.services.quiz_job_service import _run_job
from tests.fake_db import FakeDB

api_client = TestClient(app)
HEADERS = {"Authorization": f"Bearer {create_token(7, 'openid_test')}"}


def _quiz():
    return Quiz(
        quiz_id="quiz_doc",
        title="文档闯关",
        summary="",
        user_input="文档闯关",
        questions=[
            Question(
                id="q1",
                type="single",
                stem="文档里说了什么？",
                options=[Option(key="A", text="A"), Option(key="B", text="B")],
                answer=["A"],
                explanation="讲解",
                knowledge_point="知识点",
                difficulty="easy",
            )
        ],
    )


def _row(status="pending", **extra):
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


async def test_create_job_validates_and_records_document_scope(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.execute_queue = [(1, 1)]
    fake.fetch_one_queue = [_row(job_id="job_new")]
    monkeypatch.setattr(quiz_job_service, "generate_job_id", lambda: "job_new")
    validated: list[tuple] = []

    async def fake_validate(user_id, document_ids):
        validated.append((user_id, document_ids))
        return document_ids

    monkeypatch.setattr(
        quiz_job_service.knowledge_base_service,
        "validate_document_scope",
        fake_validate,
    )
    submitted: list[tuple] = []
    monkeypatch.setattr(quiz_job_service, "_submit", lambda *args: submitted.append(args))

    await quiz_job_service.create_job(
        7,
        QuizJobCreateRequest(
            user_input="文档闯关", request_id="req_1", document_ids=["doc_1"]
        ),
    )

    assert validated == [(7, ["doc_1"])]
    assert submitted[0][2].document_ids == ["doc_1"]
    _, args = fake.executed[0]
    params = json.loads(args[3])
    assert params["document_ids"] == ["doc_1"]


async def test_create_job_without_documents_skips_scope_validation(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.execute_queue = [(1, 1)]
    fake.fetch_one_queue = [_row()]
    monkeypatch.setattr(quiz_job_service, "generate_job_id", lambda: "job_new")
    called: list[bool] = []

    async def fake_validate(*args, **kwargs):
        called.append(True)
        return []

    monkeypatch.setattr(
        quiz_job_service.knowledge_base_service,
        "validate_document_scope",
        fake_validate,
    )
    monkeypatch.setattr(quiz_job_service, "_submit", lambda *args: None)

    await quiz_job_service.create_job(
        7, QuizJobCreateRequest(user_input="RAG", request_id="req_1")
    )

    assert called == []
    _, args = fake.executed[0]
    assert "document_ids" not in json.loads(args[3])


async def test_create_job_rejects_not_ready_document(monkeypatch):
    fake = FakeDB().install(monkeypatch)

    async def fake_validate(user_id, document_ids):
        raise ValidationError("文档尚未就绪，请等待处理完成后再试")

    monkeypatch.setattr(
        quiz_job_service.knowledge_base_service,
        "validate_document_scope",
        fake_validate,
    )

    with pytest.raises(ValidationError):
        await quiz_job_service.create_job(
            7,
            QuizJobCreateRequest(
                user_input="文档闯关", request_id="req_1", document_ids=["doc_1"]
            ),
        )

    assert fake.executed == []


async def test_run_job_document_scope_passes_knowledge_scope(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.execute_queue = [(0, 1), (0, 1)]
    captured: dict = {}

    def fake_generate(req, knowledge_scope=None, **kwargs):
        captured["req"] = req
        captured["scope"] = knowledge_scope
        return _quiz()

    monkeypatch.setattr(quiz_job_service, "generate_quiz", fake_generate)

    async def fake_persist(user_id, quiz):
        return None

    monkeypatch.setattr(quiz_job_service.persistence_service, "persist_quiz", fake_persist)

    await _run_job(
        "job_a", 7, QuizGenerateRequest(user_input="文档闯关", document_ids=["doc_1"])
    )

    scope = captured["scope"]
    assert isinstance(scope, KnowledgeScope)
    assert scope.user_id == 7
    assert scope.document_ids == ["doc_1"]
    assert fake.fetch_one_calls == []


async def test_run_job_without_scope_uses_ready_documents(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.execute_queue = [(0, 1), (0, 1)]
    fake.fetch_one_queue = [{"ready_count": 1}]
    captured: dict = {}

    def fake_generate(req, knowledge_scope=None, **kwargs):
        captured["scope"] = knowledge_scope
        return _quiz()

    monkeypatch.setattr(quiz_job_service, "generate_quiz", fake_generate)

    async def fake_persist(user_id, quiz):
        return None

    monkeypatch.setattr(quiz_job_service.persistence_service, "persist_quiz", fake_persist)

    await _run_job("job_a", 7, QuizGenerateRequest(user_input="RAG"))

    assert captured["scope"] is not None
    assert captured["scope"].document_ids == []
    sql, args = fake.fetch_one_calls[0]
    assert "status = 'ready'" in sql
    assert args == (7,)


async def test_run_job_without_ready_documents_keeps_old_signature(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.execute_queue = [(0, 1), (0, 1)]
    captured: list[QuizGenerateRequest] = []

    def fake_generate(req):
        captured.append(req)
        return _quiz()

    monkeypatch.setattr(quiz_job_service, "generate_quiz", fake_generate)

    async def fake_persist(user_id, quiz):
        return None

    monkeypatch.setattr(quiz_job_service.persistence_service, "persist_quiz", fake_persist)

    await _run_job("job_a", 7, QuizGenerateRequest(user_input="RAG"))

    assert len(captured) == 1


async def test_run_job_document_failure_marks_failed(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.execute_queue = [(0, 1), (0, 1)]

    def fake_generate(req, knowledge_scope=None, **kwargs):
        raise QuizGenerationError("文档内容不可用，请重新上传")

    monkeypatch.setattr(quiz_job_service, "generate_quiz", fake_generate)

    await _run_job(
        "job_a", 7, QuizGenerateRequest(user_input="文档闯关", document_ids=["doc_1"])
    )

    sql, args = fake.executed[1]
    assert "status = 'failed'" in sql
    assert args[0] == "文档内容不可用，请重新上传"


async def test_run_job_ready_lookup_failure_falls_back_without_scope(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.execute_queue = [(0, 1), (0, 1)]
    captured: list[QuizGenerateRequest] = []

    async def boom(user_id):
        raise RuntimeError("db down")

    monkeypatch.setattr(
        quiz_job_service.knowledge_document_repository, "count_ready", boom
    )

    def fake_generate(req):
        captured.append(req)
        return _quiz()

    monkeypatch.setattr(quiz_job_service, "generate_quiz", fake_generate)

    async def fake_persist(user_id, quiz):
        return None

    monkeypatch.setattr(quiz_job_service.persistence_service, "persist_quiz", fake_persist)

    await _run_job("job_a", 7, QuizGenerateRequest(user_input="RAG"))

    assert len(captured) == 1


def test_api_passes_document_ids(monkeypatch):
    captured: dict = {}

    async def fake_create(user_id, req):
        captured["user_id"] = user_id
        captured["req"] = req
        return QuizJobCreated(job_id="job_fixed", status="pending")

    monkeypatch.setattr(quiz_job_service, "create_job", fake_create)

    resp = api_client.post(
        "/api/v1/quiz/jobs",
        json={
            "user_input": "文档闯关",
            "request_id": "req_kb",
            "document_ids": ["doc_1"],
            "question_count": 5,
        },
        headers=HEADERS,
    )

    body = resp.json()
    assert body["code"] == 0
    assert body["data"] == {"job_id": "job_fixed", "status": "pending"}
    assert captured["user_id"] == 7
    assert captured["req"].document_ids == ["doc_1"]


def test_api_document_scope_rejects_foreign_document(monkeypatch):
    from app.core.exceptions import NotFoundError

    async def fake_create(user_id, req):
        raise NotFoundError("文档不存在或无权访问")

    monkeypatch.setattr(quiz_job_service, "create_job", fake_create)

    resp = api_client.post(
        "/api/v1/quiz/jobs",
        json={
            "user_input": "文档闯关",
            "request_id": "req_kb",
            "document_ids": ["doc_other"],
        },
        headers=HEADERS,
    )

    assert resp.json()["code"] == 4040
