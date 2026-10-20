import pytest
from pydantic import ValidationError

from app.models.quiz_job import QuizJobCreateRequest, QuizJobOut


def test_create_request_requires_request_id():
    with pytest.raises(ValidationError):
        QuizJobCreateRequest(user_input="什么是 RAG")


def test_create_request_question_count_out_of_bounds():
    with pytest.raises(ValidationError):
        QuizJobCreateRequest(user_input="什么是 RAG", request_id="req_1", question_count=99)


def test_create_request_defaults():
    req = QuizJobCreateRequest(user_input="什么是 RAG", request_id="req_1")
    assert req.question_count == 5
    assert req.difficulty == "mixed"
    assert req.document_ids == []


def test_create_request_accepts_document_scope():
    req = QuizJobCreateRequest(
        user_input="文档闯关", request_id="req_1", document_ids=["doc_1"]
    )
    assert req.document_ids == ["doc_1"]


def test_create_request_rejects_more_than_ten_documents():
    with pytest.raises(ValidationError):
        QuizJobCreateRequest(
            user_input="文档闯关",
            request_id="req_1",
            document_ids=[f"doc_{i}" for i in range(11)],
        )


def test_job_status_rejects_unknown_value():
    with pytest.raises(ValidationError):
        QuizJobOut(job_id="job_a", status="queued")
