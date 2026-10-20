from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.core.config import Settings
from app.core.exceptions import QuizGenerationError
from app.llm.knowledge_base import KnowledgeScope
from app.llm.output_schemas import OptionSchema, QuestionSchema, QuizOutputSchema
from app.models.quiz import QuizGenerateRequest
from app.prompts.quiz_prompt import RESEARCH_PROMPT_V2, RESEARCH_PROMPT_WITH_KB
from app.services import quiz_service
from app.services.quiz_service import generate_quiz


def _settings(**kwargs):
    values = {
        "deepseek_api_key": "test-key",
        "tavily_api_key": "tvly-test",
        "enable_web_search": True,
    }
    values.update(kwargs)
    return Settings(_env_file=None, **values)


@pytest.fixture(autouse=True)
def _configured_settings(monkeypatch):
    monkeypatch.setattr(quiz_service, "get_settings", lambda: _settings())


def _question():
    return QuestionSchema(
        id="q1",
        type="single",
        stem="RAG 是什么？",
        options=[OptionSchema(key="A", text="检索增强生成"), OptionSchema(key="B", text="数据库")],
        answer=["A"],
        explanation="RAG = 检索增强生成",
        knowledge_point="RAG",
        difficulty="easy",
    )


def _ok():
    parsed = QuizOutputSchema(
        title="RAG 入门", summary="基础", questions=[_question()]
    )
    return {"raw": object(), "parsed": parsed, "parsing_error": None}


def _kb_artifact(doc_id="doc_1"):
    return {
        "results": [
            {
                "doc_id": doc_id,
                "doc_name": "内部资料.pdf",
                "chunk_index": 0,
                "page": 2,
                "snippet": "知识库事实片段",
                "score": 0.8,
            }
        ]
    }


def _research_result(kb_doc_id="doc_1", with_kb=True, brief="【解读】按文档出题"):
    messages = [HumanMessage(content="研究一下")]
    if with_kb:
        messages.append(
            ToolMessage(
                content="知识库摘要",
                tool_call_id="1",
                name="search_knowledge_base",
                artifact=_kb_artifact(kb_doc_id),
            )
        )
    messages.append(AIMessage(content=brief))
    return {"messages": messages}


def _web_research_result():
    return {
        "messages": [
            HumanMessage(content="研究一下"),
            ToolMessage(
                content="联网摘要",
                tool_call_id="1",
                name="web_search_brief",
                artifact={
                    "results": [
                        {"title": "Example", "url": "http://example.com", "score": 0.9}
                    ]
                },
            ),
            AIMessage(content="【解读】联网结果"),
        ]
    }


class FakeAgent:
    def __init__(self, result=None, exc=None):
        self.result = result
        self.exc = exc
        self.calls = 0

    def invoke(self, payload, config=None):
        self.calls += 1
        if self.exc:
            raise self.exc
        return self.result


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


def _request():
    return QuizGenerateRequest(user_input="请根据我的文档生成闯关题目")


WEB_TOOLS = [
    SimpleNamespace(name="web_search_brief"),
    SimpleNamespace(name="web_search_full"),
    SimpleNamespace(name="web_extract"),
]
KB_TOOL = SimpleNamespace(name="search_knowledge_base")


def _patch_builders(monkeypatch, agents, web_tools=None):
    captured: list[dict] = []
    queue = list(agents)

    def fake_build_agent(llm, tools=None, system_prompt=RESEARCH_PROMPT_V2):
        captured.append({"tools": list(tools or []), "prompt": system_prompt})
        return queue.pop(0)

    monkeypatch.setattr(quiz_service, "build_research_agent", fake_build_agent)
    monkeypatch.setattr(
        quiz_service,
        "build_search_tools",
        lambda settings=None: list(WEB_TOOLS if web_tools is None else web_tools),
    )
    monkeypatch.setattr(
        quiz_service,
        "build_knowledge_base_tool",
        lambda scope, settings=None: KB_TOOL,
    )
    monkeypatch.setattr(
        quiz_service, "build_chat_model", lambda *a, **kw: object()
    )
    return captured


def test_home_mode_uses_kb_and_web_tools_with_kb_prompt(monkeypatch):
    captured = _patch_builders(monkeypatch, [FakeAgent(result=_research_result())])
    gchain = FakeChain([_ok()])

    quiz = generate_quiz(
        _request(), knowledge_scope=KnowledgeScope(user_id=7), grounded_chain=gchain
    )

    assert [tool.name for tool in captured[0]["tools"]] == [
        "search_knowledge_base",
        "web_search_brief",
        "web_search_full",
        "web_extract",
    ]
    assert captured[0]["prompt"] == RESEARCH_PROMPT_WITH_KB
    assert quiz.grounded is True
    assert quiz.sources[0].kind == "knowledge_base"


def test_home_mode_without_web_uses_kb_tool_only(monkeypatch):
    monkeypatch.setattr(
        quiz_service,
        "get_settings",
        lambda: _settings(tavily_api_key="", enable_web_search=False),
    )
    captured = _patch_builders(monkeypatch, [FakeAgent(result=_research_result())])

    generate_quiz(
        _request(),
        knowledge_scope=KnowledgeScope(user_id=7),
        grounded_chain=FakeChain([_ok()]),
    )

    assert [tool.name for tool in captured[0]["tools"]] == ["search_knowledge_base"]


def test_document_mode_uses_only_kb_tool(monkeypatch):
    captured = _patch_builders(
        monkeypatch, [FakeAgent(result=_research_result(kb_doc_id="doc_1"))]
    )

    quiz = generate_quiz(
        _request(),
        knowledge_scope=KnowledgeScope(user_id=7, document_ids=["doc_1"]),
        grounded_chain=FakeChain([_ok()]),
    )

    assert [tool.name for tool in captured[0]["tools"]] == ["search_knowledge_base"]
    assert captured[0]["prompt"] == RESEARCH_PROMPT_WITH_KB
    assert quiz.sources[0].doc_id == "doc_1"


def test_document_mode_fails_without_kb_sources(monkeypatch):
    _patch_builders(
        monkeypatch,
        [FakeAgent(result=_research_result(with_kb=False, brief="【解读】泛化内容"))],
    )
    chain = FakeChain([_ok()])

    with pytest.raises(QuizGenerationError) as excinfo:
        generate_quiz(
            _request(),
            chain=chain,
            knowledge_scope=KnowledgeScope(user_id=7, document_ids=["doc_1"]),
            grounded_chain=FakeChain([_ok()]),
        )

    assert "文档内容不可用" in excinfo.value.message
    assert chain.calls == 0


def test_document_mode_fails_when_agent_errors(monkeypatch):
    _patch_builders(monkeypatch, [FakeAgent(exc=RuntimeError("agent down"))])
    chain = FakeChain([_ok()])

    with pytest.raises(QuizGenerationError) as excinfo:
        generate_quiz(
            _request(),
            chain=chain,
            knowledge_scope=KnowledgeScope(user_id=7, document_ids=["doc_1"]),
            grounded_chain=FakeChain([_ok()]),
        )

    assert "文档出题失败" in excinfo.value.message
    assert chain.calls == 0


def test_document_mode_rejects_source_from_other_document(monkeypatch):
    _patch_builders(
        monkeypatch, [FakeAgent(result=_research_result(kb_doc_id="doc_other"))]
    )

    with pytest.raises(QuizGenerationError):
        generate_quiz(
            _request(),
            knowledge_scope=KnowledgeScope(user_id=7, document_ids=["doc_1"]),
            grounded_chain=FakeChain([_ok()]),
        )


def test_home_mode_falls_back_to_web_only_agent(monkeypatch):
    captured = _patch_builders(
        monkeypatch,
        [
            FakeAgent(exc=RuntimeError("kb agent down")),
            FakeAgent(result=_web_research_result()),
        ],
    )
    chain = FakeChain([_ok()])

    quiz = generate_quiz(
        _request(),
        chain=chain,
        knowledge_scope=KnowledgeScope(user_id=7),
        grounded_chain=FakeChain([_ok()]),
    )

    assert len(captured) == 2
    assert [tool.name for tool in captured[1]["tools"]] == [
        "web_search_brief",
        "web_search_full",
        "web_extract",
    ]
    assert captured[1]["prompt"] == RESEARCH_PROMPT_V2
    assert quiz.grounded is True
    assert quiz.sources[0].url == "http://example.com"
    assert chain.calls == 0


def test_home_mode_falls_back_to_plain_when_all_agents_fail(monkeypatch):
    _patch_builders(
        monkeypatch,
        [
            FakeAgent(exc=RuntimeError("kb agent down")),
            FakeAgent(exc=RuntimeError("web agent down")),
        ],
    )
    chain = FakeChain([_ok()])

    quiz = generate_quiz(
        _request(),
        chain=chain,
        knowledge_scope=KnowledgeScope(user_id=7),
        grounded_chain=FakeChain([_ok()]),
    )

    assert quiz.grounded is False
    assert chain.calls == 1


def test_injected_kb_tool_and_agent_skip_tool_building(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("should not build tools")

    monkeypatch.setattr(quiz_service, "build_knowledge_base_tool", boom)
    monkeypatch.setattr(quiz_service, "build_search_tools", boom)
    agent = FakeAgent(result=_research_result())

    quiz = generate_quiz(
        _request(),
        agent=agent,
        kb_tool=KB_TOOL,
        knowledge_scope=KnowledgeScope(user_id=7, document_ids=["doc_1"]),
        grounded_chain=FakeChain([_ok()]),
    )

    assert quiz.sources[0].doc_id == "doc_1"


def test_home_mode_builds_web_agent_when_kb_tool_build_fails(monkeypatch):
    captured: list[dict] = []
    agents = [FakeAgent(result=_web_research_result())]

    def boom(*args, **kwargs):
        raise RuntimeError("chroma unavailable")

    def fake_build_agent(llm, tools=None, system_prompt=RESEARCH_PROMPT_V2):
        captured.append({"tools": list(tools or []), "prompt": system_prompt})
        return agents.pop(0)

    monkeypatch.setattr(quiz_service, "build_knowledge_base_tool", boom)
    monkeypatch.setattr(quiz_service, "build_research_agent", fake_build_agent)
    monkeypatch.setattr(quiz_service, "build_search_tools", lambda settings=None: list(WEB_TOOLS))
    monkeypatch.setattr(quiz_service, "build_chat_model", lambda *a, **kw: object())

    quiz = generate_quiz(
        _request(),
        knowledge_scope=KnowledgeScope(user_id=7),
        grounded_chain=FakeChain([_ok()]),
    )

    assert [tool.name for tool in captured[0]["tools"]] == [
        "web_search_brief",
        "web_search_full",
        "web_extract",
    ]
    assert quiz.grounded is True
