"""search_tools 单测：摘要/抽取 digest、artifact、截断、工具命名与参数透传（全部用假 base，无网络）。"""

from app.llm.search_tools import (
    _extract_artifact,
    _extract_digest,
    _search_artifact,
    _search_digest,
    _truncate,
    build_search_tools,
    make_extract_tool,
    make_search_tool,
)


class FakeBase:
    def __init__(self, ret):
        self.ret = ret
        self.last_args = None

    def invoke(self, args):
        self.last_args = args
        return self.ret


def test_truncate_limits_length():
    assert _truncate("abc", 10) == "abc"
    out = _truncate("a" * 100, 10)
    assert out.startswith("a" * 10)
    assert out.endswith("…")
    assert _truncate(None, 10) == ""


def test_search_digest_includes_answer_and_truncates_body():
    raw = {
        "answer": "ANS",
        "results": [
            {"title": "T1", "url": "http://a", "content": "short", "score": 0.9},
            {"title": "T2", "url": "http://b", "raw_content": "y" * 500, "score": 0.5},
        ],
    }
    digest = _search_digest(raw, 50)
    assert "ANS" in digest
    assert "http://a" in digest
    assert "short" in digest
    # 第二条正文被截断
    assert "y" * 51 not in digest
    assert "…" in digest


def test_search_digest_handles_error_and_empty():
    assert "出错" in _search_digest({"error": "boom"}, 50)
    assert _search_digest({"results": []}, 50) == "[无搜索结果]"
    assert "未成功" in _search_digest("some error string", 50)


def test_search_artifact_maps_results_and_skips_missing_url():
    raw = {
        "answer": "ANS",
        "results": [
            {"title": "T1", "url": "http://a", "score": 0.9},
            {"title": "no-url", "score": 0.1},
        ],
    }
    art = _search_artifact(raw)
    assert art["answer"] == "ANS"
    assert art["results"] == [{"title": "T1", "url": "http://a", "score": 0.9}]


def test_extract_digest_and_artifact():
    raw = {
        "results": [{"url": "http://p", "raw_content": "z" * 300}],
        "failed_results": ["http://bad"],
    }
    digest = _extract_digest(raw, 40)
    assert "http://p" in digest
    assert "z" * 41 not in digest
    assert "http://bad" in digest
    art = _extract_artifact(raw)
    assert art["results"] == [{"title": "http://p", "url": "http://p"}]
    assert art["failed_results"] == ["http://bad"]


def test_make_search_tool_name_format_and_arg_passthrough():
    base = FakeBase({"results": [{"title": "T", "url": "http://a", "content": "c", "score": 0.7}]})
    t = make_search_tool("web_search_brief", "desc", base, 100)
    assert t.name == "web_search_brief"
    assert t.response_format == "content_and_artifact"
    # 直接调底层 func 拿到 (content, artifact) 元组
    content, artifact = t.func(query="q", time_range="week")
    assert "http://a" in content
    assert artifact["results"][0]["url"] == "http://a"
    # 动态参数透传给底层
    assert base.last_args == {"query": "q", "time_range": "week"}


def test_make_search_tool_swallows_base_exception():
    class Boom:
        def invoke(self, args):
            raise RuntimeError("net down")

    t = make_search_tool("web_search_full", "desc", Boom(), 100)
    content, artifact = t.func(query="q")
    assert "失败" in content
    assert artifact == {"results": []}


def test_make_extract_tool_name_and_passthrough():
    base = FakeBase({"results": [{"url": "http://p", "raw_content": "body"}], "failed_results": []})
    t = make_extract_tool("web_extract", "desc", base, 100)
    assert t.name == "web_extract"
    content, artifact = t.func(urls=["http://p"], extract_depth="advanced")
    assert "http://p" in content
    assert artifact["results"][0]["url"] == "http://p"
    assert base.last_args == {"urls": ["http://p"], "extract_depth": "advanced"}


def test_build_search_tools_three_unique_names():
    tools = build_search_tools()
    names = [t.name for t in tools]
    assert names == ["web_search_brief", "web_search_full", "web_extract"]
    assert len(set(names)) == 3
    assert all(t.response_format == "content_and_artifact" for t in tools)
