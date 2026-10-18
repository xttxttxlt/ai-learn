from app.models.quiz import Option, Question
from app.models.report import AnswerRecord
from app.services.scoring_service import compute_score, is_record_correct


def _q(qid, kp, answer, qtype="single"):
    options = (
        [Option(key="A", text="a"), Option(key="B", text="b")]
        if qtype != "multiple"
        else [Option(key="A", text="a"), Option(key="B", text="b"), Option(key="C", text="c")]
    )
    return Question(
        id=qid, type=qtype, stem="s", options=options, answer=answer,
        explanation="e", knowledge_point=kp, difficulty="easy",
    )


def test_all_correct():
    qs = [_q("q1", "KP1", ["A"]), _q("q2", "KP2", ["B"])]
    recs = [
        AnswerRecord(question_id="q1", selected_answers=["A"], is_correct=True, duration_ms=1000),
        AnswerRecord(question_id="q2", selected_answers=["B"], is_correct=True, duration_ms=2000),
    ]
    s = compute_score(qs, recs)
    assert (s.total, s.correct, s.accuracy) == (2, 2, 100)
    assert s.mastered_points == ["KP1", "KP2"]
    assert s.weak_points == []
    assert s.total_duration_ms == 3000


def test_all_wrong():
    s = compute_score([_q("q1", "KP1", ["A"])],
                      [AnswerRecord(question_id="q1", selected_answers=["B"], is_correct=False)])
    assert s.accuracy == 0
    assert s.weak_points == ["KP1"]
    assert s.mastered_points == []


def test_mixed_accuracy_rounding():
    qs = [_q("q1", "KP1", ["A"]), _q("q2", "KP2", ["A"]), _q("q3", "KP3", ["A"])]
    recs = [
        AnswerRecord(question_id="q1", selected_answers=["A"], is_correct=True),
        AnswerRecord(question_id="q2", selected_answers=["B"], is_correct=False),
        AnswerRecord(question_id="q3", selected_answers=["B"], is_correct=False),
    ]
    s = compute_score(qs, recs)
    assert s.correct == 1
    assert s.accuracy == 33  # round(1/3*100)


def test_recomputes_correctness_ignoring_frontend_flag():
    # 前端谎报 is_correct=True，但答案其实错 -> 服务端以重算为准
    s = compute_score([_q("q1", "KP1", ["A"])],
                      [AnswerRecord(question_id="q1", selected_answers=["B"], is_correct=True)])
    assert s.correct == 0
    assert s.weak_points == ["KP1"]


def test_falls_back_to_flag_when_question_missing():
    s = compute_score([], [AnswerRecord(question_id="qX", selected_answers=["A"], is_correct=True)])
    assert (s.total, s.correct) == (1, 1)


def test_multiple_answer_set_comparison():
    q = _q("q1", "KP", ["A", "C"], qtype="multiple")
    assert is_record_correct(AnswerRecord(question_id="q1", selected_answers=["C", "A"]), q) is True
    assert is_record_correct(AnswerRecord(question_id="q1", selected_answers=["A"]), q) is False


def test_knowledge_point_in_both_goes_to_weak():
    qs = [_q("q1", "KP", ["A"]), _q("q2", "KP", ["A"])]
    recs = [
        AnswerRecord(question_id="q1", selected_answers=["A"], is_correct=True),
        AnswerRecord(question_id="q2", selected_answers=["B"], is_correct=False),
    ]
    s = compute_score(qs, recs)
    assert "KP" in s.weak_points
    assert "KP" not in s.mastered_points


def test_empty_records():
    s = compute_score([], [])
    assert (s.total, s.accuracy) == (0, 0)
