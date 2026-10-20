import chromadb
import pytest

from app.core.config import Settings
from app.llm.document_parser import DocumentChunk
from app.llm.knowledge_base import (
    EmbeddingServiceError,
    KnowledgeVectorStore,
)


class FakeEmbeddings:
    """确定性二维向量：alpha -> [1,0]，beta -> [0,1]，其他 -> 混合。"""

    def __init__(self, dim=2):
        self.dim = dim
        self.batches: list[int] = []

    def _vec(self, text: str):
        if self.dim != 2:
            return [1.0] * self.dim
        if "alpha" in text:
            return [1.0, 0.0]
        if "beta" in text:
            return [0.0, 1.0]
        return [0.7, 0.7]

    def embed_documents(self, texts):
        self.batches.append(len(texts))
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


def _settings(**kwargs):
    values = {
        "dashscope_api_key": "test-key",
        "embedding_dimensions": 2,
        "embedding_batch_size": 2,
        "kb_retrieval_top_k": 4,
    }
    values.update(kwargs)
    return Settings(_env_file=None, **values)


def _store(tmp_path, embeddings=None, settings=None):
    client = chromadb.PersistentClient(path=str(tmp_path / "chroma"))
    return KnowledgeVectorStore(
        client=client,
        embeddings=embeddings or FakeEmbeddings(),
        settings=settings or _settings(),
    )


def _chunks(*texts):
    return [
        DocumentChunk(text=text, metadata={"chunk_index": i})
        for i, text in enumerate(texts)
    ]


def test_add_chunks_returns_count_and_persists_metadata(tmp_path):
    store = _store(tmp_path)

    count = store.add_chunks(7, "doc_1", "笔记.md", _chunks("alpha", "beta"))

    assert count == 2
    results = store.search(7, "alpha query", top_k=5)
    assert {r.doc_id for r in results} == {"doc_1"}
    assert {r.doc_name for r in results} == {"笔记.md"}
    assert {r.chunk_index for r in results} == {0, 1}


def test_search_sorts_by_cosine_relevance(tmp_path):
    store = _store(tmp_path)
    store.add_chunks(7, "doc_1", "笔记.md", _chunks("alpha 内容", "beta 内容"))

    results = store.search(7, "alpha query", top_k=5)

    assert [r.text for r in results] == ["alpha 内容", "beta 内容"]
    assert results[0].score == pytest.approx(1.0, abs=1e-4)
    assert results[1].score == pytest.approx(0.0, abs=1e-4)
    assert results[0].snippet == "alpha 内容"


def test_search_filters_by_document_ids(tmp_path):
    store = _store(tmp_path)
    store.add_chunks(7, "doc_1", "一.md", _chunks("alpha"))
    store.add_chunks(7, "doc_2", "二.md", _chunks("alpha"))

    results = store.search(7, "alpha", top_k=5, document_ids=["doc_2"])

    assert [r.doc_id for r in results] == ["doc_2"]


def test_users_are_isolated(tmp_path):
    store = _store(tmp_path)
    store.add_chunks(7, "doc_1", "七.md", _chunks("alpha"))
    store.add_chunks(8, "doc_2", "八.md", _chunks("alpha"))

    results = store.search(7, "alpha", top_k=5)

    assert [r.doc_id for r in results] == ["doc_1"]


def test_delete_document_removes_all_chunks(tmp_path):
    store = _store(tmp_path)
    store.add_chunks(7, "doc_1", "一.md", _chunks("alpha", "beta"))
    store.add_chunks(7, "doc_2", "二.md", _chunks("alpha"))

    store.delete_document(7, "doc_1")

    results = store.search(7, "alpha", top_k=5)
    assert [r.doc_id for r in results] == ["doc_2"]


def test_delete_document_is_idempotent(tmp_path):
    store = _store(tmp_path)
    store.delete_document(7, "missing")
    store.delete_document(7, "missing")


def test_search_before_any_write_returns_empty(tmp_path):
    store = _store(tmp_path)
    assert store.search(7, "alpha") == []


def test_data_survives_reopen(tmp_path):
    store = _store(tmp_path)
    store.add_chunks(7, "doc_1", "笔记.md", _chunks("alpha"))

    reopened = _store(tmp_path)
    results = reopened.search(7, "alpha", top_k=5)

    assert len(results) == 1
    assert results[0].doc_id == "doc_1"


def test_page_metadata_is_preserved(tmp_path):
    store = _store(tmp_path)
    chunks = [DocumentChunk(text="alpha", metadata={"chunk_index": 0, "page": 3})]

    store.add_chunks(7, "doc_1", "文档.pdf", chunks)
    results = store.search(7, "alpha", top_k=1)

    assert results[0].page == 3


def test_blank_query_returns_empty(tmp_path):
    store = _store(tmp_path)
    store.add_chunks(7, "doc_1", "笔记.md", _chunks("alpha"))
    assert store.search(7, "   ") == []


def test_embedding_dimension_mismatch_raises_readable_error(tmp_path):
    store = _store(tmp_path, embeddings=FakeEmbeddings(dim=3), settings=_settings(embedding_dimensions=2))

    with pytest.raises(EmbeddingServiceError) as excinfo:
        store.add_chunks(7, "doc_1", "笔记.md", _chunks("alpha"))

    assert "维度" in str(excinfo.value)


def test_embeddings_are_batched(tmp_path):
    fake = FakeEmbeddings()
    store = _store(tmp_path, embeddings=fake, settings=_settings(embedding_batch_size=2))

    store.add_chunks(7, "doc_1", "笔记.md", _chunks("alpha", "beta", "alpha2", "beta2", "alpha3"))

    assert fake.batches == [2, 2, 1]
