from app.core.config import Settings
from app.llm.knowledge_base import (
    KnowledgeScope,
    KnowledgeSearchResult,
    build_knowledge_base_tool,
)


def _settings(**kwargs):
    return Settings(
        _env_file=None,
        dashscope_api_key="test-key",
        kb_retrieval_top_k=4,
        **kwargs,
    )


class FakeStore:
    def __init__(self, results=None, error=None):
        self.results = results or []
        self.error = error
        self.calls: list[dict] = []

    def search(self, user_id, query, top_k=None, document_ids=None):
        self.calls.append(
            {
                "user_id": user_id,
                "query": query,
                "top_k": top_k,
                "document_ids": document_ids,
            }
        )
        if self.error:
            raise self.error
        return self.results


def _result(**kwargs):
    values = {
        "doc_id": "doc_1",
        "doc_name": "内部资料.pdf",
        "chunk_index": 2,
        "page": 5,
        "text": "知识库片段正文",
        "snippet": "知识库片段",
        "score": 0.71,
    }
    values.update(kwargs)
    return KnowledgeSearchResult(**values)


def test_tool_name_and_response_format():
    tool = build_knowledge_base_tool(
        KnowledgeScope(user_id=7), settings=_settings(), store=FakeStore()
    )

    assert tool.name == "search_knowledge_base"
    assert tool.response_format == "content_and_artifact"
    assert "知识库" in tool.description


def test_tool_returns_content_and_artifact():
    store = FakeStore(results=[_result()])
    tool = build_knowledge_base_tool(
        KnowledgeScope(user_id=7), settings=_settings(), store=store
    )

    content, artifact = tool.func(query="RAG 是什么")

    assert store.calls == [
        {
            "user_id": 7,
            "query": "RAG 是什么",
            "top_k": 4,
            "document_ids": None,
        }
    ]
    assert "内部资料.pdf" in content
    assert "第 5 页" in content
    assert "知识库片段" in content
    assert artifact == {
        "results": [
            {
                "doc_id": "doc_1",
                "doc_name": "内部资料.pdf",
                "chunk_index": 2,
                "page": 5,
                "snippet": "知识库片段",
                "score": 0.71,
            }
        ]
    }


def test_tool_omits_page_when_missing():
    tool = build_knowledge_base_tool(
        KnowledgeScope(user_id=7),
        settings=_settings(),
        store=FakeStore(results=[_result(page=None)]),
    )

    content, artifact = tool.func(query="RAG")

    assert "第" not in content
    assert artifact["results"][0]["page"] is None


def test_tool_returns_empty_marker_without_results():
    tool = build_knowledge_base_tool(
        KnowledgeScope(user_id=7), settings=_settings(), store=FakeStore()
    )

    content, artifact = tool.func(query="不存在的内容")

    assert content == "[知识库无相关结果]"
    assert artifact == {"results": []}


def test_home_mode_filters_low_relevance_results():
    store = FakeStore(
        results=[
            _result(score=0.81, snippet="高相关片段"),
            _result(doc_id="doc_2", chunk_index=4, score=0.59, snippet="低相关片段"),
        ]
    )
    tool = build_knowledge_base_tool(
        KnowledgeScope(user_id=7), settings=_settings(), store=store
    )

    content, artifact = tool.func(query="RAG 是什么")

    assert "高相关片段" in content
    assert "低相关片段" not in content
    assert len(artifact["results"]) == 1
    assert artifact["results"][0]["score"] == 0.81


def test_home_mode_returns_insufficient_marker_when_all_below_threshold():
    store = FakeStore(
        results=[_result(score=0.331), _result(doc_id="doc_2", chunk_index=4, score=0.274)]
    )
    tool = build_knowledge_base_tool(
        KnowledgeScope(user_id=7), settings=_settings(), store=store
    )

    content, artifact = tool.func(query="常见动漫人物")

    assert content.startswith("[知识库无足够相关内容]")
    assert "0.33" in content
    assert "0.60" in content
    assert artifact == {"results": []}


def test_document_mode_returns_insufficient_marker_when_below_threshold():
    store = FakeStore(results=[_result(score=0.33)])
    tool = build_knowledge_base_tool(
        KnowledgeScope(user_id=7, document_ids=["doc_1"]),
        settings=_settings(),
        store=store,
    )

    content, artifact = tool.func(query="文档外的主题")

    assert content.startswith("[知识库无足够相关内容]")
    assert artifact == {"results": []}


def test_tool_swallows_search_exception():
    tool = build_knowledge_base_tool(
        KnowledgeScope(user_id=7),
        settings=_settings(),
        store=FakeStore(error=RuntimeError("secret-internal-stack")),
    )

    content, artifact = tool.func(query="RAG")

    assert content.startswith("[知识库检索失败]")
    assert "secret" not in content
    assert artifact == {"results": []}


def test_tool_passes_document_scope():
    store = FakeStore(results=[_result()])
    tool = build_knowledge_base_tool(
        KnowledgeScope(user_id=7, document_ids=["doc_1", "doc_2"]),
        settings=_settings(),
        store=store,
    )

    tool.func(query="RAG")

    assert store.calls[0]["document_ids"] == ["doc_1", "doc_2"]
