import pytest
from pydantic import ValidationError

from app.models.quiz_job import QuizJobCreateRequest


def _req(**kw):
    return QuizJobCreateRequest(user_input="什么是 RAG", request_id="req_modes", **kw)


def test_defaults_all_sources_off():
    req = _req()
    assert req.use_web_search is False
    assert req.use_knowledge_base is False
    assert req.document_id is None
    assert req.generate_images is False


def test_web_only_is_valid():
    req = _req(use_web_search=True)
    assert req.use_web_search is True
    assert req.use_knowledge_base is False
    assert req.document_id is None


def test_knowledge_base_only_is_valid():
    req = _req(use_knowledge_base=True, document_id="doc_1")
    assert req.use_knowledge_base is True
    assert req.document_id == "doc_1"


def test_web_and_knowledge_base_are_mutually_exclusive():
    with pytest.raises(ValidationError):
        _req(use_web_search=True, use_knowledge_base=True, document_id="doc_1")


def test_knowledge_base_requires_document():
    with pytest.raises(ValidationError):
        _req(use_knowledge_base=True)


def test_document_requires_knowledge_base_flag():
    with pytest.raises(ValidationError):
        _req(document_id="doc_1")


def test_legacy_document_ids_is_rejected():
    with pytest.raises(ValidationError):
        _req(document_ids=["doc_1"])
