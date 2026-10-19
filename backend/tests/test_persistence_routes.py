"""quiz/report 路由的可选鉴权 + 落库触发测试（不动现有 test_quiz_api / test_report_api）。"""

from fastapi.testclient import TestClient

import app.api.v1.routes.quiz as quiz_route
import app.api.v1.routes.report as report_route
from app.core.auth import create_token
from app.main import app
from app.models.quiz import Option, Question, Quiz
from app.models.report import Report

client = TestClient(app)

HEADERS = {"Authorization": f"Bearer {create_token(7, 'openid_test')}"}


def _fake_quiz():
    return Quiz(
        quiz_id="quiz_t1",
        title="RAG 入门",
        summary="s",
        source_type="text",
        user_input="什么是 RAG",
        questions=[
            Question(
                id="q1",
                type="single",
                stem="题干",
                options=[Option(key="A", text="a"), Option(key="B", text="b")],
                answer=["A"],
                explanation="讲解",
                knowledge_point="kp",
                difficulty="easy",
            )
        ],
    )


def _fake_report():
    return Report(accuracy=100, three_line_summary=["x"], share_quote="y")


def test_quiz_generate_with_token_persists(monkeypatch):
    calls = []
    monkeypatch.setattr(quiz_route, "generate_quiz", lambda req: _fake_quiz())

    async def fake_persist(user_id, quiz):
        calls.append((user_id, quiz.quiz_id))

    monkeypatch.setattr(quiz_route.persistence_service, "persist_quiz", fake_persist)
    resp = client.post(
        "/api/v1/quiz/generate", json={"user_input": "什么是 RAG"}, headers=HEADERS
    )
    assert resp.json()["code"] == 0
    assert calls == [(7, "quiz_t1")]


def test_quiz_generate_anonymous_skips_persist(monkeypatch):
    calls = []
    monkeypatch.setattr(quiz_route, "generate_quiz", lambda req: _fake_quiz())

    async def fake_persist(user_id, quiz):
        calls.append(user_id)

    monkeypatch.setattr(quiz_route.persistence_service, "persist_quiz", fake_persist)
    resp = client.post("/api/v1/quiz/generate", json={"user_input": "什么是 RAG"})
    assert resp.json()["code"] == 0
    assert calls == []


def test_quiz_generate_bad_token_still_works_anonymously(monkeypatch):
    monkeypatch.setattr(quiz_route, "generate_quiz", lambda req: _fake_quiz())
    resp = client.post(
        "/api/v1/quiz/generate",
        json={"user_input": "什么是 RAG"},
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert resp.json()["code"] == 0


def test_report_generate_with_token_persists(monkeypatch):
    calls = []
    monkeypatch.setattr(report_route, "generate_report", lambda req: _fake_report())

    async def fake_persist(user_id, req, report):
        calls.append((user_id, req.quiz_id))

    monkeypatch.setattr(report_route.persistence_service, "persist_report", fake_persist)
    resp = client.post(
        "/api/v1/report/generate",
        json={
            "quiz_id": "quiz_t1",
            "topic": "RAG",
            "questions": [_fake_quiz().questions[0].model_dump()],
            "answer_records": [
                {"question_id": "q1", "selected_answers": ["A"], "is_correct": True, "duration_ms": 1}
            ],
        },
        headers=HEADERS,
    )
    assert resp.json()["code"] == 0
    assert calls == [(7, "quiz_t1")]


def test_report_generate_anonymous_skips_persist(monkeypatch):
    calls = []
    monkeypatch.setattr(report_route, "generate_report", lambda req: _fake_report())

    async def fake_persist(user_id, req, report):
        calls.append(user_id)

    monkeypatch.setattr(report_route.persistence_service, "persist_report", fake_persist)
    resp = client.post(
        "/api/v1/report/generate",
        json={
            "quiz_id": "quiz_t1",
            "topic": "RAG",
            "questions": [_fake_quiz().questions[0].model_dump()],
            "answer_records": [
                {"question_id": "q1", "selected_answers": ["A"], "is_correct": True, "duration_ms": 1}
            ],
        },
    )
    assert resp.json()["code"] == 0
    assert calls == []


def test_quiz_progress_endpoint_saves(monkeypatch):
    calls = []

    async def fake_save(quiz_id, user_id, index, records):
        calls.append((quiz_id, user_id, index, len(records)))

    monkeypatch.setattr(quiz_route.quiz_repository, "save_progress", fake_save)
    resp = client.post(
        "/api/v1/quiz/progress",
        json={
            "quiz_id": "quiz_t1",
            "index": 2,
            "records": [
                {"question_id": "q1", "selected_answers": ["A"], "is_correct": True, "duration_ms": 5}
            ],
        },
        headers=HEADERS,
    )
    assert resp.json()["code"] == 0
    assert calls == [("quiz_t1", 7, 2, 1)]


def test_quiz_progress_endpoint_requires_auth(monkeypatch):
    resp = client.post(
        "/api/v1/quiz/progress", json={"quiz_id": "quiz_t1", "index": 0, "records": []}
    )
    assert resp.json()["code"] == 4010
