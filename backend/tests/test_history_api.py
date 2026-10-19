import json
from datetime import datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from app.core.auth import create_token
from app.main import app
from tests.fake_db import FakeDB

client = TestClient(app)

HEADERS = {"Authorization": f"Bearer {create_token(7, 'openid_test')}"}

QUESTIONS = [
    {
        "id": "q1",
        "type": "single",
        "stem": "RAG 是什么？",
        "options": [{"key": "A", "text": "检索增强生成"}, {"key": "B", "text": "数据库"}],
        "answer": ["A"],
        "explanation": "RAG=检索增强生成",
        "knowledge_point": "RAG 定义",
        "difficulty": "easy",
    }
]


def test_list_quizzes_pagination(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.fetch_one_queue = [{"total": 3}]
    fake.fetch_all_queue = [
        [
            {
                "quiz_id": "quiz_a",
                "title": "RAG 入门",
                "created_at": datetime(2026, 10, 19, 10, 0, 0),
                "accuracy": Decimal("80.00"),
                "total_questions": 5,
            },
            {
                "quiz_id": "quiz_b",
                "title": "未完成的局",
                "created_at": datetime(2026, 10, 18, 9, 0, 0),
                "accuracy": None,
                "total_questions": None,
            },
        ]
    ]
    resp = client.get("/api/v1/user/quizzes?page=1&page_size=2", headers=HEADERS)
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["total"] == 3
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert data["items"][0]["quiz_id"] == "quiz_a"
    assert data["items"][0]["accuracy"] == 80
    assert data["items"][0]["created_at"] == "2026-10-19 10:00:00"
    # 未完成答题的记录 accuracy 为 None
    assert data["items"][1]["accuracy"] is None
    # LIMIT/OFFSET 传参正确
    _, args = fake.fetch_all_calls[0]
    assert args == (7, 2, 0)


def test_quiz_detail_success(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    report_json = {
        "accuracy": 80,
        "mastered_points": ["RAG 定义"],
        "weak_points": [],
        "three_line_summary": ["a", "b", "c"],
        "advice": ["复习"],
        "share_quote": "金句",
    }
    records_json = [
        {"question_id": "q1", "selected_answers": ["A"], "is_correct": True, "duration_ms": 100}
    ]
    fake.fetch_one_queue = [
        {  # quiz_sessions
            "quiz_id": "quiz_a",
            "user_id": 7,
            "title": "RAG 入门",
            "summary": "摘要",
            "questions_json": json.dumps(QUESTIONS, ensure_ascii=False),
            "created_at": datetime(2026, 10, 19, 10, 0, 0),
        },
        {  # answer_records
            "quiz_id": "quiz_a",
            "records_json": json.dumps(records_json, ensure_ascii=False),
            "total_questions": 1,
            "correct_count": 1,
            "accuracy": Decimal("100.00"),
        },
        {  # reports
            "quiz_id": "quiz_a",
            "report_json": json.dumps(report_json, ensure_ascii=False),
        },
    ]
    resp = client.get("/api/v1/user/quizzes/quiz_a", headers=HEADERS)
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["quiz_id"] == "quiz_a"
    assert data["title"] == "RAG 入门"
    assert data["questions"][0]["stem"] == "RAG 是什么？"
    assert data["answer_records"][0]["is_correct"] is True
    assert data["report"]["share_quote"] == "金句"
    assert data["accuracy"] == 100
    assert data["created_at"] == "2026-10-19 10:00:00"


def test_quiz_detail_not_found(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.fetch_one_queue = [None]
    resp = client.get("/api/v1/user/quizzes/quiz_missing", headers=HEADERS)
    assert resp.json()["code"] == 4040


def test_quiz_detail_without_answer_and_report(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.fetch_one_queue = [
        {
            "quiz_id": "quiz_c",
            "user_id": 7,
            "title": "只出题未作答",
            "summary": None,
            "questions_json": json.dumps(QUESTIONS, ensure_ascii=False),
            "created_at": datetime(2026, 10, 19),
        },
        None,  # answer_records
        None,  # reports
    ]
    resp = client.get("/api/v1/user/quizzes/quiz_c", headers=HEADERS)
    data = resp.json()["data"]
    assert data["answer_records"] == []
    assert data["report"] is None
    assert data["accuracy"] is None
    assert data["summary"] == ""
