import pytest
from fastapi.testclient import TestClient

from app.core.auth import create_token
from app.main import app
from app.models.quiz import Option, Question, Quiz
from app.services import quiz_job_service

client = TestClient(app)

HEADERS = {"Authorization": f"Bearer {create_token(7, 'openid_test')}"}
OTHER_HEADERS = {"Authorization": f"Bearer {create_token(8, 'openid_other')}"}


class InMemoryJobRepo:
    def __init__(self):
        self.rows: dict[tuple[int, str], dict] = {}

    async def create_job(self, job_id, user_id, request_id, params):
        key = (user_id, request_id)
        if key in self.rows:
            return 0
        self.rows[key] = {
            "job_id": job_id,
            "user_id": user_id,
            "request_id": request_id,
            "status": "pending",
            "params_json": params,
            "result_json": None,
            "error_message": None,
        }
        return 1

    async def get_by_request(self, user_id, request_id):
        return self.rows.get((user_id, request_id))

    async def get_job(self, job_id, user_id):
        for row in self.rows.values():
            if row["job_id"] == job_id and row["user_id"] == user_id:
                return row
        return None

    async def fail_if_timed_out(self, job_id, user_id, timeout_seconds):
        return 0


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


@pytest.fixture
def job_repo(monkeypatch):
    repo = InMemoryJobRepo()
    for name in ("create_job", "get_by_request", "get_job", "fail_if_timed_out"):
        monkeypatch.setattr(quiz_job_service.quiz_job_repository, name, getattr(repo, name))
    monkeypatch.setattr(quiz_job_service, "_submit", lambda *args: None)
    return repo


def _create(question_count=5):
    return client.post(
        "/api/v1/quiz/jobs",
        json={"user_input": "什么是 RAG", "request_id": "req_1", "question_count": question_count},
        headers=HEADERS,
    )


def test_create_job_returns_job_id(job_repo):
    resp = _create()

    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["job_id"].startswith("job_")
    assert body["data"]["status"] == "pending"


def test_create_job_requires_login(job_repo):
    resp = client.post(
        "/api/v1/quiz/jobs", json={"user_input": "什么是 RAG", "request_id": "req_1"}
    )

    assert resp.status_code == 200
    assert resp.json()["code"] == 4010


@pytest.mark.parametrize(
    "payload",
    [
        {"user_input": "什么是 RAG"},
        {"user_input": "", "request_id": "req_1"},
        {"user_input": "什么是 RAG", "request_id": "req_1", "question_count": 99},
    ],
)
def test_create_job_validation_errors(job_repo, payload):
    resp = client.post("/api/v1/quiz/jobs", json=payload, headers=HEADERS)

    assert resp.status_code == 200
    assert resp.json()["code"] == 4000


def test_create_job_is_idempotent_by_request_id(job_repo):
    first = _create().json()["data"]
    second = _create().json()["data"]

    assert first["job_id"] == second["job_id"]
    assert len(job_repo.rows) == 1


def test_get_pending_and_running_job(job_repo):
    job_id = _create().json()["data"]["job_id"]

    pending = client.get(f"/api/v1/quiz/jobs/{job_id}", headers=HEADERS).json()["data"]
    assert pending["status"] == "pending"
    assert pending["quiz"] is None

    job_repo.rows[(7, "req_1")]["status"] = "running"
    running = client.get(f"/api/v1/quiz/jobs/{job_id}", headers=HEADERS).json()["data"]
    assert running["status"] == "running"
    assert running["quiz"] is None


def test_get_completed_job_returns_quiz(job_repo):
    job_id = _create().json()["data"]["job_id"]
    row = job_repo.rows[(7, "req_1")]
    row["status"] = "completed"
    row["result_json"] = _quiz().model_dump()

    data = client.get(f"/api/v1/quiz/jobs/{job_id}", headers=HEADERS).json()["data"]

    assert data["status"] == "completed"
    assert data["quiz"]["quiz_id"] == "quiz_test"
    assert data["error"] is None


def test_get_failed_job_returns_error(job_repo):
    job_id = _create().json()["data"]["job_id"]
    row = job_repo.rows[(7, "req_1")]
    row["status"] = "failed"
    row["error_message"] = "题库生成失败，请稍后重试"

    data = client.get(f"/api/v1/quiz/jobs/{job_id}", headers=HEADERS).json()["data"]

    assert data["status"] == "failed"
    assert data["error"] == "题库生成失败，请稍后重试"
    assert data["quiz"] is None


def test_get_job_is_owner_scoped(job_repo):
    job_id = _create().json()["data"]["job_id"]

    other = client.get(f"/api/v1/quiz/jobs/{job_id}", headers=OTHER_HEADERS).json()
    missing = client.get("/api/v1/quiz/jobs/job_missing", headers=HEADERS).json()

    assert other["code"] == 4040
    assert missing["code"] == 4040


def test_sync_generate_endpoint_removed(job_repo):
    resp = client.post(
        "/api/v1/quiz/generate",
        json={"user_input": "什么是 RAG"},
        headers=HEADERS,
    )

    assert resp.status_code == 404


def test_create_job_accepts_generate_images(job_repo):
    resp = client.post(
        "/api/v1/quiz/jobs",
        json={
            "user_input": "什么是 RAG",
            "request_id": "req_1",
            "generate_images": True,
        },
        headers=HEADERS,
    )

    assert resp.json()["code"] == 0
    assert job_repo.rows[(7, "req_1")]["params_json"]["generate_images"] is True


def test_get_completed_job_returns_image_url(job_repo):
    job_id = _create().json()["data"]["job_id"]
    quiz = _quiz()
    quiz.questions[0].image_url = "https://cdn.example.com/q1.png"
    row = job_repo.rows[(7, "req_1")]
    row["status"] = "completed"
    row["result_json"] = quiz.model_dump()

    data = client.get(f"/api/v1/quiz/jobs/{job_id}", headers=HEADERS).json()["data"]

    assert data["quiz"]["questions"][0]["image_url"] == "https://cdn.example.com/q1.png"
