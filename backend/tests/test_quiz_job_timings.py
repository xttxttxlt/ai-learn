import json
import time
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.core.config import Settings
from app.core.exceptions import QuizGenerationError
from app.llm.knowledge_base import KnowledgeScope
from app.llm.output_schemas import OptionSchema, QuestionSchema, QuizOutputSchema
from app.models.quiz import Option, Question, Quiz, QuizGenerateRequest
from app.repositories import quiz_job_repository as repo
from app.services import quiz_job_service
from app.services.quiz_job_service import _run_job
from app.services.quiz_service import generate_quiz
from tests.fake_db import FakeDB


def _quiz():
    return Quiz(
        quiz_id="quiz_test",
        title="RAG 入门",
        summary="",
        user_input="RAG",
        questions=[
            Question(
                id="q1",
                type="single",
                stem="RAG 是什么？",
                options=[Option(key="A", text="检索增强生成"), Option(key="B", text="数据库")],
                answer=["A"],
                explanation="讲解",
                knowledge_point="RAG",
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


def _settings(**kwargs):
    values = {"deepseek_api_key": "test-key", "tavily_api_key": "tvly-test", "enable_web_search": True}
    values.update(kwargs)
    return Settings(_env_file=None, **values)


def _ok():
    parsed = QuizOutputSchema(
        title="RAG 入门",
        summary="",
        questions=[
            QuestionSchema(
                id="q1",
                type="single",
                stem="RAG 是什么？",
                options=[OptionSchema(key="A", text="检索增强生成"), OptionSchema(key="B", text="数据库")],
                answer=["A"],
                explanation="讲解",
                knowledge_point="RAG",
                difficulty="easy",
            )
        ],
    )
    return {"raw": object(), "parsed": parsed, "parsing_error": None}


class FakeChain:
    def __init__(self, result=None):
        self.result = result or _ok()
        self.calls = 0

    def invoke(self, payload):
        self.calls += 1
        return self.result


class FakeAgent:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def invoke(self, payload, config=None):
        self.calls += 1
        return self.result


async def test_run_job_records_timings_on_success(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.execute_queue = [(0, 1), (0, 1)]

    def fake_generate(req, timings=None, **kwargs):
        timings["path"] = "plain"
        timings["research_ms"] = 0
        return _quiz()

    async def fake_persist(user_id, quiz):
        return None

    monkeypatch.setattr(quiz_job_service, "generate_quiz", fake_generate)
    monkeypatch.setattr(quiz_job_service.persistence_service, "persist_quiz", fake_persist)

    await _run_job(
        "job_a",
        7,
        QuizGenerateRequest(user_input="RAG"),
        submitted_at=time.perf_counter() - 0.01,
    )

    sql, args = fake.executed[1]
    assert "timings_json = %s" in sql
    timings = json.loads(args[1])
    for key in (
        "queue_ms",
        "validate_scope_ms",
        "generate_ms",
        "images_ms",
        "persist_ms",
        "total_ms",
        "question_count",
        "source_count",
        "grounded",
    ):
        assert key in timings
    assert timings["path"] == "plain"
    assert timings["question_count"] == 1
    assert timings["source_count"] == 0
    assert timings["grounded"] is False
    assert timings["total_ms"] >= 0


async def test_run_job_records_partial_timings_on_failure(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.execute_queue = [(0, 1), (0, 1)]

    def fake_generate(req, timings=None, **kwargs):
        timings["path"] = "plain"
        raise QuizGenerationError()

    monkeypatch.setattr(quiz_job_service, "generate_quiz", fake_generate)

    await _run_job(
        "job_a",
        7,
        QuizGenerateRequest(user_input="RAG"),
        submitted_at=time.perf_counter() - 0.01,
    )

    sql, args = fake.executed[1]
    assert "timings_json = %s" in sql
    timings = json.loads(args[1])
    assert timings["error_stage"] == "generate"
    assert timings["generate_ms"] >= 0
    assert timings["total_ms"] >= 0
    assert "question_count" not in timings


def test_grounded_quiz_records_research_and_phase2(monkeypatch):
    monkeypatch.setattr("app.services.quiz_service.get_settings", lambda: _settings())
    messages = [
        HumanMessage(content="研究"),
        ToolMessage(
            content="搜索",
            tool_call_id="1",
            name="web_search_brief",
            artifact={"results": [{"title": "A", "url": "http://a", "score": 0.9}]},
        ),
        ToolMessage(
            content="抽取",
            tool_call_id="2",
            name="web_extract",
            artifact={"results": [{"title": "B", "url": "http://b"}]},
        ),
        AIMessage(content="中间结论"),
        AIMessage(content="【解读】联网结果"),
    ]
    timings: dict = {}

    quiz = generate_quiz(
        QuizGenerateRequest(user_input="RAG", use_web_search=True),
        agent=FakeAgent(result={"messages": messages}),
        grounded_chain=FakeChain(),
        timings=timings,
    )

    assert quiz.grounded is True
    assert timings["path"] == "web"
    assert timings["research_ms"] >= 0
    assert timings["phase2_ms"] >= 0
    assert timings["research_llm_calls"] == 2
    assert timings["research_tool_calls"] == 2
    assert timings["phase2_attempts"] == 1


def test_knowledge_base_fallback_records_path_and_reason(monkeypatch):
    monkeypatch.setattr("app.services.quiz_service.get_settings", lambda: _settings())
    monkeypatch.setattr(
        "app.services.quiz_service.build_research_agent",
        lambda *args, **kwargs: FakeAgent(
            result={
                "messages": [
                    HumanMessage(content="研究"),
                    AIMessage(content="【解读】泛化内容"),
                ]
            }
        ),
    )
    monkeypatch.setattr(
        "app.services.quiz_service.build_knowledge_base_tool",
        lambda *args, **kwargs: SimpleNamespace(name="search_knowledge_base"),
    )
    monkeypatch.setattr("app.services.quiz_service.build_chat_model", lambda *a, **kw: object())
    timings: dict = {}

    quiz = generate_quiz(
        QuizGenerateRequest(
            user_input="RAG", use_knowledge_base=True, document_id="doc_1"
        ),
        knowledge_scope=KnowledgeScope(user_id=7, document_ids=["doc_1"]),
        chain=FakeChain(),
        grounded_chain=FakeChain(),
        timings=timings,
    )

    assert quiz.grounded is False
    assert timings["path"] == "knowledge_base_fallback_plain"
    assert timings["fallback_reason"]
    assert timings["research_ms"] >= 0


def test_plain_quiz_records_path_only():
    timings: dict = {}
    quiz = generate_quiz(
        QuizGenerateRequest(user_input="RAG"), chain=FakeChain(), timings=timings
    )

    assert quiz.grounded is False
    assert timings["path"] == "plain"
    assert "research_ms" not in timings
    assert "phase2_ms" not in timings


async def test_repository_mark_completed_writes_timings(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.execute_queue = [(0, 1)]

    await repo.mark_completed("job_a", 7, {"quiz_id": "q"}, timings={"total_ms": 12})

    sql, args = fake.executed[0]
    assert "timings_json = %s" in sql
    assert args[0] == '{"quiz_id": "q"}'
    assert args[1] == '{"total_ms": 12}'


async def test_repository_mark_completed_without_timings_writes_null(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.execute_queue = [(0, 1)]

    await repo.mark_completed("job_a", 7, {"quiz_id": "q"})

    sql, args = fake.executed[0]
    assert "timings_json = %s" in sql
    assert args[1] is None


async def test_repository_mark_failed_writes_timings(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.execute_queue = [(0, 1)]

    await repo.mark_failed("job_a", 7, "失败", timings={"total_ms": 9})

    sql, args = fake.executed[0]
    assert "timings_json = %s" in sql
    assert args[0] == "失败"
    assert args[1] == '{"total_ms": 9}'
