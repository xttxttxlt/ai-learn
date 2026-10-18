import pytest

from app.core.exceptions import ReportGenerationError, ValidationError
from app.llm.output_schemas import ReportOutputSchema
from app.models.quiz import Option, Question
from app.models.report import AnswerRecord, ReportGenerateRequest
from app.services.report_service import generate_report


def _q(qid="q1", kp="KP1", answer=None):
    return Question(
        id=qid, type="single", stem="s",
        options=[Option(key="A", text="a"), Option(key="B", text="b")],
        answer=answer or ["A"], explanation="e", knowledge_point=kp, difficulty="easy",
    )


def _parsed(accuracy=50):
    return ReportOutputSchema(
        accuracy=accuracy, mastered_points=["LLM掌握的"], weak_points=["LLM薄弱的"],
        three_line_summary=["句1", "句2", "句3"], advice=["建议1", "建议2"],
        share_quote="学习金句",
    )


def _ok(parsed=None):
    return {"raw": object(), "parsed": parsed or _parsed(), "parsing_error": None}


class FakeChain:
    def __init__(self, results):
        self.results = list(results)
        self.calls = 0

    def invoke(self, payload):
        item = self.results[min(self.calls, len(self.results) - 1)]
        self.calls += 1
        if isinstance(item, Exception):
            raise item
        return item


def _request(records=None, questions=None):
    questions = questions if questions is not None else [_q()]
    records = records if records is not None else [
        AnswerRecord(question_id="q1", selected_answers=["A"], is_correct=True)
    ]
    return ReportGenerateRequest(
        quiz_id="quiz_1", topic="RAG", questions=questions, answer_records=records
    )


def test_success_uses_local_numbers_and_llm_prose():
    # 本地：1 题答对 -> accuracy=100, mastered=[KP1]；LLM 的数值应被本地覆盖
    chain = FakeChain([_ok(_parsed(accuracy=50))])
    report = generate_report(_request(), chain=chain)
    assert report.accuracy == 100
    assert report.mastered_points == ["KP1"]
    assert report.weak_points == []
    assert report.three_line_summary == ["句1", "句2", "句3"]
    assert report.advice == ["建议1", "建议2"]
    assert report.share_quote == "学习金句"


def test_empty_records_raises_validation():
    with pytest.raises(ValidationError):
        generate_report(_request(records=[]), chain=FakeChain([_ok()]))


def test_all_attempts_fail_raises():
    chain = FakeChain([RuntimeError("fail")])
    with pytest.raises(ReportGenerationError):
        generate_report(_request(), chain=chain)
    assert chain.calls == 3


def test_parsing_error_retries_then_fail():
    chain = FakeChain([{"raw": object(), "parsed": None, "parsing_error": ValueError("bad")}])
    with pytest.raises(ReportGenerationError):
        generate_report(_request(), chain=chain)
    assert chain.calls == 3


def test_incomplete_parsed_raises():
    bad = ReportOutputSchema(accuracy=80, mastered_points=[], weak_points=[],
                             three_line_summary=[], advice=[], share_quote="")
    with pytest.raises(ReportGenerationError):
        generate_report(_request(), chain=FakeChain([_ok(bad)]))


def test_retries_then_succeeds():
    chain = FakeChain([RuntimeError("x"), _ok()])
    report = generate_report(_request(), chain=chain)
    assert report.share_quote == "学习金句"
    assert chain.calls == 2


def test_accepts_direct_parsed():
    report = generate_report(_request(), chain=FakeChain([_parsed()]))
    assert report.accuracy == 100
