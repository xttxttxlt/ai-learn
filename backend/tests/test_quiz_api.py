from fastapi.testclient import TestClient

import app.api.v1.routes.quiz as quiz_route
from app.core.exceptions import QuizGenerationError
from app.main import app
from app.models.quiz import Option, Question, Quiz

client = TestClient(app)


def _fake_quiz():
    return Quiz(
        quiz_id="quiz_test123",
        title="RAG 入门",
        summary="基础题",
        source_type="text",
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


def test_generate_success(monkeypatch):
    monkeypatch.setattr(quiz_route, "generate_quiz", lambda req: _fake_quiz())
    resp = client.post("/api/v1/quiz/generate", json={"user_input": "什么是 RAG"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["quiz_id"] == "quiz_test123"
    assert data["title"] == "RAG 入门"
    assert len(data["questions"]) == 1
    assert data["questions"][0]["answer"] == ["A"]
    assert data["questions"][0]["options"][0]["key"] == "A"


def test_generate_empty_input_returns_4000():
    resp = client.post("/api/v1/quiz/generate", json={"user_input": ""})
    assert resp.status_code == 200
    assert resp.json()["code"] == 4000


def test_generate_missing_field_returns_4000():
    resp = client.post("/api/v1/quiz/generate", json={})
    assert resp.status_code == 200
    assert resp.json()["code"] == 4000


def test_generate_question_count_out_of_bounds_returns_4000():
    resp = client.post(
        "/api/v1/quiz/generate", json={"user_input": "x", "question_count": 99}
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == 4000


def test_generate_service_error_returns_4001(monkeypatch):
    def boom(req):
        raise QuizGenerationError()

    monkeypatch.setattr(quiz_route, "generate_quiz", boom)
    resp = client.post("/api/v1/quiz/generate", json={"user_input": "什么是 RAG"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 4001
    assert body["data"] is None


def test_generate_includes_grounding_fields(monkeypatch):
    from app.models.quiz import Source

    def grounded(req):
        q = _fake_quiz()
        q.interpretation = "按 AI 智能体工程领域"
        q.grounded = True
        q.sources = [Source(title="Faros", url="http://faros", score=0.94, kind="search")]
        return q

    monkeypatch.setattr(quiz_route, "generate_quiz", grounded)
    resp = client.post("/api/v1/quiz/generate", json={"user_input": "Harness Engineering"})
    data = resp.json()["data"]
    assert data["grounded"] is True
    assert data["interpretation"] == "按 AI 智能体工程领域"
    assert data["sources"][0]["url"] == "http://faros"


def test_generate_default_grounding_fields(monkeypatch):
    # 降级态：未接地时 grounded=False、sources=[]、interpretation=""
    monkeypatch.setattr(quiz_route, "generate_quiz", lambda req: _fake_quiz())
    resp = client.post("/api/v1/quiz/generate", json={"user_input": "什么是 RAG"})
    data = resp.json()["data"]
    assert data["grounded"] is False
    assert data["sources"] == []
    assert data["interpretation"] == ""
