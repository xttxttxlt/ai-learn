from fastapi.testclient import TestClient

import app.api.v1.routes.report as report_route
from app.core.exceptions import ReportGenerationError
from app.main import app
from app.models.report import Report

client = TestClient(app)


def _fake_report():
    return Report(
        accuracy=100, mastered_points=["KP1"], weak_points=[],
        three_line_summary=["句1", "句2", "句3"], advice=["建议1"], share_quote="金句",
    )


def test_generate_success(monkeypatch):
    monkeypatch.setattr(report_route, "generate_report", lambda req: _fake_report())
    resp = client.post(
        "/api/v1/report/generate",
        json={"quiz_id": "quiz_1", "topic": "RAG", "questions": [], "answer_records": []},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["accuracy"] == 100
    assert body["data"]["share_quote"] == "金句"
    assert body["data"]["three_line_summary"] == ["句1", "句2", "句3"]


def test_empty_records_returns_4000():
    # 不 mock，走真实 service：answer_records 为空 -> ValidationError -> 4000（不触发 LLM）
    resp = client.post(
        "/api/v1/report/generate",
        json={"quiz_id": "quiz_1", "topic": "RAG", "questions": [], "answer_records": []},
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == 4000


def test_service_error_returns_4002(monkeypatch):
    def boom(req):
        raise ReportGenerationError()

    monkeypatch.setattr(report_route, "generate_report", boom)
    resp = client.post(
        "/api/v1/report/generate",
        json={
            "quiz_id": "quiz_1",
            "topic": "RAG",
            "questions": [],
            "answer_records": [
                {"question_id": "q1", "selected_answers": ["A"], "is_correct": True}
            ],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == 4002
    assert resp.json()["data"] is None
