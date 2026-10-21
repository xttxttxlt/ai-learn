import json

from app.models.quiz import Option, Question, Quiz
from app.models.report import AnswerRecord, Report, ReportGenerateRequest
from app.services import persistence_service
from tests.fake_db import FakeDB


def _quiz(quiz_id="quiz_p1"):
    return Quiz(
        quiz_id=quiz_id,
        title="RAG 入门",
        summary="摘要",
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
                knowledge_point="知识点",
                difficulty="easy",
            )
        ],
    )


def _report_request(quiz_id="quiz_p1", correct=2, total=3):
    records = [
        AnswerRecord(question_id=f"q{i+1}", selected_answers=["A"], is_correct=i < correct)
        for i in range(total)
    ]
    return ReportGenerateRequest(
        quiz_id=quiz_id,
        topic="RAG 入门",
        questions=[_quiz(quiz_id).questions[0]] * total,
        answer_records=records,
    )


def _report(accuracy=67):
    return Report(accuracy=accuracy, three_line_summary=["x"], share_quote="y")


async def test_persist_quiz_writes_session(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    await persistence_service.persist_quiz(7, _quiz())
    assert len(fake.executed) == 1
    sql, args = fake.executed[0]
    assert "INSERT INTO quiz_sessions" in sql
    assert args[0] == "quiz_p1"
    assert args[1] == 7
    assert json.loads(args[5])[0]["id"] == "q1"


async def test_persist_quiz_writes_image_url(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    quiz = _quiz()
    quiz.questions[0].image_url = "https://cdn.example.com/q1.png"

    await persistence_service.persist_quiz(7, quiz)

    _, args = fake.executed[0]
    assert json.loads(args[5])[0]["image_url"] == "https://cdn.example.com/q1.png"


async def test_persist_quiz_swallows_db_error(monkeypatch):
    fake = FakeDB().install(monkeypatch)

    async def boom(sql, args=None):
        raise RuntimeError("db down")

    import app.core.db as db

    monkeypatch.setattr(db, "execute", boom)
    await persistence_service.persist_quiz(7, _quiz())  # 不抛出即通过


async def test_persist_report_new_record_adds_coins(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.fetch_one_queue = [{"quiz_id": "quiz_p1"}]  # 会话已存在
    fake.execute_queue = [(1, 1), (1, 1), (0, 1)]  # record 新插入 / report / coins
    await persistence_service.persist_report(7, _report_request(correct=2), _report())

    sqls = [sql for sql, _ in fake.executed]
    assert any("INSERT INTO answer_records" in s for s in sqls)
    assert any("INSERT INTO reports" in s for s in sqls)
    coin_calls = [(s, a) for s, a in fake.executed if "total_coins" in s]
    assert len(coin_calls) == 1
    assert coin_calls[0][1] == (20, 7)  # 2 题 × 10 金币


async def test_persist_report_duplicate_skips_coins(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.fetch_one_queue = [{"quiz_id": "quiz_p1"}]
    fake.execute_queue = [(1, 2), (1, 2)]  # ON DUPLICATE 覆盖更新，rowcount=2
    await persistence_service.persist_report(7, _report_request(correct=2), _report())
    assert not any("total_coins" in sql for sql, _ in fake.executed)


async def test_persist_report_creates_missing_session(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.fetch_one_queue = [None]  # 会话不存在（匿名出题后登录）
    fake.execute_queue = [(1, 1), (2, 1), (2, 1), (0, 1)]
    await persistence_service.persist_report(7, _report_request(correct=1), _report())
    sqls = [sql for sql, _ in fake.executed]
    assert any("INSERT INTO quiz_sessions" in s for s in sqls)
    assert any("INSERT INTO answer_records" in s for s in sqls)


async def test_persist_report_skips_without_quiz_id(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    await persistence_service.persist_report(7, _report_request(quiz_id=""), _report())
    assert fake.executed == []


async def test_persist_report_zero_correct_no_coins(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.fetch_one_queue = [{"quiz_id": "quiz_p1"}]
    fake.execute_queue = [(1, 1), (1, 1)]
    await persistence_service.persist_report(7, _report_request(correct=0), _report(accuracy=0))
    assert not any("total_coins" in sql for sql, _ in fake.executed)


def _grounded_quiz(quiz_id="quiz_g1"):
    from app.models.quiz import Source

    return Quiz(
        quiz_id=quiz_id,
        title="T",
        summary="s",
        interpretation="按 X 领域",
        source_type="text",
        user_input="u",
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
        sources=[Source(title="S", url="http://s", score=0.9, kind="search")],
        grounded=True,
    )


async def test_persist_quiz_writes_grounding_fields(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    await persistence_service.persist_quiz(7, _grounded_quiz())
    sql, args = fake.executed[0]
    assert "interpretation" in sql and "sources_json" in sql and "grounded" in sql
    # 新列追加在 questions_json(args[5]) 之后，保持既有索引不变
    assert args[6] == "按 X 领域"
    assert json.loads(args[7])[0]["url"] == "http://s"
    assert args[8] == 1
