"""quiz_agent 单测：研究 Agent 组装（离线编译）、研究简报文本抽取、来源确定性抽取。"""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from app.llm.quiz_agent import (
    build_research_agent,
    extract_research_text,
    extract_sources_from_messages,
)


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
