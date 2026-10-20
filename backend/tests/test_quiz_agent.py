"""quiz_agent 单测：研究 Agent 组装（离线编译）、研究简报文本抽取、来源确定性抽取。"""

from langchain.agents.middleware import ToolCallLimitMiddleware
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from app.llm import quiz_agent
from app.llm.quiz_agent import (
    build_research_agent,
    extract_research_text,
    extract_sources_from_messages,
)
from app.models.quiz import Source
from app.prompts.quiz_prompt import RESEARCH_PROMPT_V2


@tool(response_format="content_and_artifact")
def _fake_tool(q: str) -> tuple[str, dict]:
    "fake grounding tool"
    return "digest", {"results": [{"title": "T", "url": "http://a", "score": 0.8}]}


def _llm():
    return ChatOpenAI(
        model="deepseek-flash",
        base_url="https://api.deepseek.com",
        api_key="dummy-key",
        temperature=0.4,
    )


def test_build_research_agent_compiles_with_tools():
    agent = build_research_agent(_llm(), tools=[_fake_tool])
    assert hasattr(agent, "invoke")


def test_build_research_agent_applies_tool_call_limit(monkeypatch):
    captured: dict = {}

    def fake_create_agent(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(quiz_agent, "create_agent", fake_create_agent)

    build_research_agent(_llm(), tools=[_fake_tool], tool_call_limit=7)

    middleware = captured["middleware"]
    assert len(middleware) == 1
    limiter = middleware[0]
    assert isinstance(limiter, ToolCallLimitMiddleware)
    assert limiter.run_limit == 7
    assert limiter.exit_behavior == "continue"


def test_build_research_agent_accepts_custom_system_prompt(monkeypatch):
    captured: dict = {}

    def fake_create_agent(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(quiz_agent, "create_agent", fake_create_agent)

    build_research_agent(_llm(), tools=[_fake_tool], system_prompt="custom prompt")
    assert captured["system_prompt"] == "custom prompt"

    build_research_agent(_llm(), tools=[_fake_tool])
    assert captured["system_prompt"] == RESEARCH_PROMPT_V2


def _tm(name, artifact, content="d", call_id="c"):
    return ToolMessage(content=content, tool_call_id=call_id, name=name, artifact=artifact)


def test_extract_research_text_prefers_last_ai_message():
    msgs = [
        HumanMessage(content="研究一下"),
        _tm("web_search_brief", {"results": []}, content="搜索摘要"),
        AIMessage(content=""),  # 只有 tool_calls 的空 AI 消息应被跳过
        AIMessage(content="【解读】按 AI 智能体工程领域"),
    ]
    assert extract_research_text(msgs) == "【解读】按 AI 智能体工程领域"


def test_extract_research_text_falls_back_to_tool_digests():
    msgs = [
        HumanMessage(content="x"),
        _tm("web_search_brief", {"results": []}, content="摘要A"),
        _tm("web_extract", {"results": []}, content="正文B"),
    ]
    text = extract_research_text(msgs)
    assert "摘要A" in text and "正文B" in text


def test_extract_research_text_empty():
    assert extract_research_text([]) == ""
    assert extract_research_text(None) == ""


def test_extract_sources_orders_extract_first_then_score_desc():
    msgs = [
        AIMessage(content="x"),
        _tm("web_search_brief", {"results": [{"title": "S1", "url": "http://s1", "score": 0.5}]}, call_id="1"),
        _tm("web_extract", {"results": [{"title": "P", "url": "http://p"}]}, call_id="2"),
        _tm("web_search_full", {"results": [{"title": "S2", "url": "http://s2", "score": 0.7}]}, call_id="3"),
    ]
    srcs = extract_sources_from_messages(msgs)
    assert [s["url"] for s in srcs] == ["http://p", "http://s2", "http://s1"]
    assert srcs[0]["kind"] == "extract"
    assert srcs[1]["kind"] == "search"


def test_extract_sources_dedups_by_url_first_wins():
    msgs = [
        _tm("web_search_brief", {"results": [
            {"title": "A", "url": "http://x", "score": 0.3},
            {"title": "B", "url": "http://x", "score": 0.9},
        ]}, call_id="1"),
    ]
    srcs = extract_sources_from_messages(msgs)
    assert len(srcs) == 1
    assert srcs[0]["title"] == "A"  # 首次出现优先


def test_extract_sources_skips_missing_artifact_and_url():
    msgs = [
        ToolMessage(content="no artifact", tool_call_id="1", name="web_search_brief"),
        _tm("web_search_brief", {"results": [{"title": "no-url", "score": 0.1}]}, call_id="2"),
    ]
    assert extract_sources_from_messages(msgs) == []


def test_extract_sources_handles_all_extract_failed():
    msgs = [_tm("web_extract", {"results": [], "failed_results": ["http://bad"]}, call_id="1")]
    assert extract_sources_from_messages(msgs) == []


def test_extract_sources_truncation():
    msgs = [
        _tm("web_search_brief", {"results": [
            {"title": f"T{i}", "url": f"http://u{i}", "score": 0.1 * i} for i in range(10)
        ]}, call_id="1"),
    ]
    assert len(extract_sources_from_messages(msgs, max_sources=6)) == 6


def test_source_model_allows_empty_url_and_kb_fields():
    source = Source(
        title="笔记.md",
        kind="knowledge_base",
        doc_id="doc_1",
        chunk_index=3,
        page=2,
        snippet="片段",
        score=0.9,
    )

    assert source.url == ""
    assert source.doc_id == "doc_1"
    assert source.chunk_index == 3
    assert source.page == 2


def test_extract_sources_maps_knowledge_base_and_orders_first():
    msgs = [
        _tm(
            "web_search_brief",
            {"results": [{"title": "S", "url": "http://s", "score": 0.99}]},
            call_id="1",
        ),
        _tm(
            "search_knowledge_base",
            {
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
            },
            call_id="2",
        ),
    ]

    sources = extract_sources_from_messages(msgs)

    assert sources[0]["kind"] == "knowledge_base"
    assert sources[0]["title"] == "内部资料.pdf"
    assert sources[0]["url"] == ""
    assert sources[0]["doc_id"] == "doc_1"
    assert sources[0]["chunk_index"] == 2
    assert sources[0]["page"] == 5
    assert sources[0]["snippet"] == "知识库片段"
    assert sources[1]["url"] == "http://s"


def test_extract_sources_dedups_knowledge_base_by_doc_and_chunk():
    msgs = [
        _tm(
            "search_knowledge_base",
            {
                "results": [
                    {"doc_id": "doc_1", "doc_name": "A", "chunk_index": 0, "snippet": "first", "score": 0.5},
                    {"doc_id": "doc_1", "doc_name": "A", "chunk_index": 0, "snippet": "second", "score": 0.9},
                    {"doc_id": "doc_1", "doc_name": "A", "chunk_index": 1, "snippet": "other", "score": 0.8},
                ]
            },
            call_id="1",
        ),
    ]

    sources = extract_sources_from_messages(msgs)

    assert len(sources) == 2
    by_chunk = {s["chunk_index"]: s["snippet"] for s in sources}
    assert by_chunk[0] == "first"
    assert by_chunk[1] == "other"
    assert [s["chunk_index"] for s in sources] == [1, 0]  # 组内按相关度降序


def test_extract_sources_skips_kb_results_without_doc_id():
    msgs = [
        _tm(
            "search_knowledge_base",
            {"results": [{"doc_name": "A", "chunk_index": 0, "snippet": "x", "score": 0.5}]},
            call_id="1",
        ),
    ]

    assert extract_sources_from_messages(msgs) == []
