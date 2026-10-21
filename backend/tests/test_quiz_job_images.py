import json

from app.models.quiz import Option, Question, Quiz, QuizGenerateRequest
from app.models.quiz_job import QuizJobCreateRequest
from app.services import history_service, quiz_job_service
from app.services.quiz_job_service import _run_job
from tests.fake_db import FakeDB


def _quiz(image_url=None):
    return Quiz(
        quiz_id="quiz_test",
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
                image_url=image_url,
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


async def test_create_job_persists_generate_images(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.execute_queue = [(1, 1)]
    fake.fetch_one_queue = [_row("pending", job_id="job_new")]
    monkeypatch.setattr(quiz_job_service, "generate_job_id", lambda: "job_new")
    submitted: list[tuple] = []
    monkeypatch.setattr(quiz_job_service, "_submit", lambda *args: submitted.append(args))

    await quiz_job_service.create_job(
        7,
        QuizJobCreateRequest(
            user_input="什么是 RAG", request_id="req_1", generate_images=True
        ),
    )

    assert len(submitted) == 1
    assert submitted[0][2].generate_images is True
    _, args = fake.executed[0]
    assert '"generate_images": true' in args[3]


async def test_create_job_forces_generate_images_off_for_document_scope(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.execute_queue = [(1, 1)]
    fake.fetch_one_queue = [_row("pending", job_id="job_new")]
    monkeypatch.setattr(quiz_job_service, "generate_job_id", lambda: "job_new")
    submitted: list[tuple] = []
    monkeypatch.setattr(quiz_job_service, "_submit", lambda *args: submitted.append(args))

    async def fake_validate(user_id, document_ids):
        return document_ids

    monkeypatch.setattr(
        quiz_job_service.knowledge_base_service, "validate_document_scope", fake_validate
    )

    await quiz_job_service.create_job(
        7,
        QuizJobCreateRequest(
            user_input="文档出题",
            request_id="req_1",
            use_knowledge_base=True,
            document_id="doc_1",
            generate_images=True,
        ),
    )

    assert submitted[0][2].generate_images is False
    _, args = fake.executed[0]
    assert json.loads(args[3])["generate_images"] is False


async def test_run_job_attaches_images_after_generation_and_before_persist(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.execute_queue = [(0, 1), (0, 1)]
    quiz = _quiz()
    order: list[str] = []
    persisted: list[Quiz] = []

    def fake_generate(req, **kwargs):
        order.append("generate")
        return quiz

    async def fake_attach(user_id, q):
        order.append("images")
        q.questions[0].image_url = "https://cdn.example.com/q1.png"
        return q

    async def fake_persist(user_id, q):
        order.append("persist")
        persisted.append(q)

    monkeypatch.setattr(quiz_job_service, "generate_quiz", fake_generate)
    monkeypatch.setattr(quiz_job_service.image_generation_service, "attach_images", fake_attach)
    monkeypatch.setattr(quiz_job_service.persistence_service, "persist_quiz", fake_persist)

    await _run_job(
        "job_a", 7, QuizGenerateRequest(user_input="RAG", generate_images=True)
    )

    assert order == ["generate", "images", "persist"]
    assert persisted[0].questions[0].image_url == "https://cdn.example.com/q1.png"
    _, args = fake.executed[1]
    assert '"image_url": "https://cdn.example.com/q1.png"' in args[0]


async def test_run_job_skips_images_when_disabled(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.execute_queue = [(0, 1), (0, 1)]
    calls: list[str] = []

    monkeypatch.setattr(quiz_job_service, "generate_quiz", lambda req, **kwargs: _quiz())

    async def fake_attach(user_id, q):
        calls.append("images")
        return q

    async def fake_persist(user_id, q):
        calls.append("persist")

    monkeypatch.setattr(quiz_job_service.image_generation_service, "attach_images", fake_attach)
    monkeypatch.setattr(quiz_job_service.persistence_service, "persist_quiz", fake_persist)

    await _run_job("job_a", 7, QuizGenerateRequest(user_input="RAG"))

    assert calls == ["persist"]


async def test_run_job_skips_images_for_document_scope(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.execute_queue = [(0, 1), (0, 1)]
    calls: list[str] = []

    def fake_generate(req, **kwargs):
        return _quiz()

    async def fake_attach(user_id, q):
        calls.append("images")
        return q

    async def fake_persist(user_id, q):
        calls.append("persist")

    async def fake_validate(user_id, document_ids):
        return document_ids

    monkeypatch.setattr(
        quiz_job_service.knowledge_base_service, "validate_document_scope", fake_validate
    )
    monkeypatch.setattr(quiz_job_service, "generate_quiz", fake_generate)
    monkeypatch.setattr(quiz_job_service.image_generation_service, "attach_images", fake_attach)
    monkeypatch.setattr(quiz_job_service.persistence_service, "persist_quiz", fake_persist)

    await _run_job(
        "job_a",
        7,
        QuizGenerateRequest(
            user_input="文档出题",
            use_knowledge_base=True,
            document_id="doc_1",
            generate_images=True,
        ),
    )

    assert calls == ["persist"]


async def test_run_job_completes_when_image_attachment_raises(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.execute_queue = [(0, 1), (0, 1)]
    persisted: list[str] = []

    monkeypatch.setattr(quiz_job_service, "generate_quiz", lambda req, **kwargs: _quiz())

    async def boom_attach(user_id, q):
        raise RuntimeError("image service down")

    async def fake_persist(user_id, q):
        persisted.append(q.quiz_id)

    monkeypatch.setattr(quiz_job_service.image_generation_service, "attach_images", boom_attach)
    monkeypatch.setattr(quiz_job_service.persistence_service, "persist_quiz", fake_persist)

    await _run_job(
        "job_a", 7, QuizGenerateRequest(user_input="RAG", generate_images=True)
    )

    assert persisted == ["quiz_test"]
    assert "status = 'completed'" in fake.executed[1][0]


async def test_history_detail_returns_image_url(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    image_url = "https://cdn.example.com/question-images/q1.png"
    questions = [
        {
            "id": "q1",
            "type": "single",
            "stem": "apple 的中文意思？",
            "options": [{"key": "A", "text": "苹果"}, {"key": "B", "text": "香蕉"}],
            "answer": ["A"],
            "explanation": "apple 意为苹果",
            "knowledge_point": "apple 词义",
            "difficulty": "easy",
            "image_url": image_url,
        }
    ]
    fake.fetch_one_queue = [
        {
            "quiz_id": "quiz_img",
            "user_id": 7,
            "title": "单词闯关",
            "summary": "",
            "questions_json": json.dumps(questions, ensure_ascii=False),
            "created_at": "2026-10-21 10:00:00",
        },
        None,
        None,
    ]

    detail = await history_service.get_detail(7, "quiz_img")

    assert detail.questions[0].image_url == image_url
    assert detail.questions[0].model_dump()["image_url"] == image_url
