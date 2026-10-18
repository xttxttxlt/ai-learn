import pytest

from app.core.exceptions import ContentFilteredError, QuizGenerationError, ValidationError
from app.llm.output_schemas import OptionSchema, QuestionSchema, QuizOutputSchema
from app.models.quiz import QuizGenerateRequest
from app.services.quiz_service import generate_quiz


def _question(qid="q1", qtype="single", answer=None, options=None):
    options = options or [
        OptionSchema(key="A", text="检索增强生成"),
        OptionSchema(key="B", text="一种数据库"),
    ]
    answer = answer or ["A"]
    return QuestionSchema(
        id=qid,
        type=qtype,
        stem="RAG 是什么？",
        options=options,
        answer=answer,
        explanation="RAG = 检索增强生成",
        knowledge_point="RAG 定义",
        difficulty="easy",
    )


def _parsed(questions=None):
    return QuizOutputSchema(
        title="RAG 入门",
        summary="围绕 RAG 的基础题",
        questions=questions if questions is not None else [_question()],
    )


def _ok_result(parsed=None):
    return {"raw": object(), "parsed": parsed or _parsed(), "parsing_error": None}


class FakeChain:
    """按序返回预置结果；元素为 Exception 时抛出。超出长度则重复最后一个。"""

    def __init__(self, results):
        self.results = list(results)
        self.calls = 0

    def invoke(self, payload):
        item = self.results[min(self.calls, len(self.results) - 1)]
        self.calls += 1
        if isinstance(item, Exception):
            raise item
        return item


def _request(**kw):
    return QuizGenerateRequest(user_input=kw.pop("user_input", "什么是 RAG"), **kw)


def test_success_maps_domain_model():
    chain = FakeChain([_ok_result()])
    quiz = generate_quiz(_request(), chain=chain)
    assert quiz.quiz_id.startswith("quiz_")
    assert quiz.title == "RAG 入门"
    assert quiz.source_type == "text"
    assert len(quiz.questions) == 1
    q = quiz.questions[0]
    assert q.type == "single"
    assert q.answer == ["A"]
    assert q.options[0].key == "A"
    assert chain.calls == 1


def test_cleans_input_before_chain():
    captured = {}

    class CapturingChain:
        def invoke(self, payload):
            captured.update(payload)
            return _ok_result()

    generate_quiz(_request(user_input="  什么是   RAG  "), chain=CapturingChain())
    assert captured["user_input"] == "什么是 RAG"
    assert captured["question_count"] == 5


def test_empty_input_raises_validation():
    with pytest.raises(ValidationError):
        generate_quiz(_request(user_input="   "), chain=FakeChain([_ok_result()]))


def test_sensitive_input_raises_content_filtered():
    with pytest.raises(ContentFilteredError):
        generate_quiz(_request(user_input="赌博网站怎么建"), chain=FakeChain([_ok_result()]))


def test_retries_then_succeeds():
    chain = FakeChain([RuntimeError("boom"), RuntimeError("boom again"), _ok_result()])
    quiz = generate_quiz(_request(), chain=chain)
    assert quiz.title == "RAG 入门"
    assert chain.calls == 3


def test_all_attempts_fail_raises_quiz_error():
    chain = FakeChain([RuntimeError("always fail")])
    with pytest.raises(QuizGenerationError):
        generate_quiz(_request(), chain=chain)
    assert chain.calls == 3  # llm_max_retries 默认 2 -> 共 3 次


def test_parsing_error_triggers_retry_then_fail():
    chain = FakeChain(
        [{"raw": object(), "parsed": None, "parsing_error": ValueError("bad json")}]
    )
    with pytest.raises(QuizGenerationError):
        generate_quiz(_request(), chain=chain)
    assert chain.calls == 3


def test_answer_option_mismatch_raises():
    chain = FakeChain([_ok_result(_parsed([_question(answer=["Z"])]))])
    with pytest.raises(QuizGenerationError):
        generate_quiz(_request(), chain=chain)


def test_single_with_two_answers_raises():
    chain = FakeChain([_ok_result(_parsed([_question(qtype="single", answer=["A", "B"])]))])
    with pytest.raises(QuizGenerationError):
        generate_quiz(_request(), chain=chain)


def test_multiple_needs_two_answers():
    chain = FakeChain([_ok_result(_parsed([_question(qtype="multiple", answer=["A"])]))])
    with pytest.raises(QuizGenerationError):
        generate_quiz(_request(), chain=chain)


def test_judge_question_valid():
    judge = _question(
        qtype="judge",
        answer=["A"],
        options=[OptionSchema(key="A", text="正确"), OptionSchema(key="B", text="错误")],
    )
    quiz = generate_quiz(_request(), chain=FakeChain([_ok_result(_parsed([judge]))]))
    assert quiz.questions[0].type == "judge"
    assert quiz.questions[0].answer == ["A"]


def test_accepts_direct_parsed_result():
    # 兼容 chain 直接返回 parsed（非 include_raw 字典）
    quiz = generate_quiz(_request(), chain=FakeChain([_parsed()]))
    assert quiz.title == "RAG 入门"


def test_empty_questions_raises():
    chain = FakeChain([_ok_result(_parsed(questions=[]))])
    with pytest.raises(QuizGenerationError):
        generate_quiz(_request(), chain=chain)


def test_missing_answer_key_raises():
    # 选项 key 重复也应判为不合法
    dup = _question(options=[OptionSchema(key="A", text="x"), OptionSchema(key="A", text="y")])
    chain = FakeChain([_ok_result(_parsed([dup]))])
    with pytest.raises(QuizGenerationError):
        generate_quiz(_request(), chain=chain)
