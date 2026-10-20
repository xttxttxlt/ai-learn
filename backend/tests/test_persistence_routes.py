"""quiz/report 路由的鉴权与落库触发测试。

出题落库已迁入异步任务执行器，由 test_quiz_job_service 覆盖；本文件保留报告与进度接口的用例。
"""

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
