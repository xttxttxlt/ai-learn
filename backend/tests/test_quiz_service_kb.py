from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.core.config import Settings
from app.core.exceptions import ValidationError
from app.llm.knowledge_base import KnowledgeScope
from app.llm.output_schemas import OptionSchema, QuestionSchema, QuizOutputSchema
from app.models.quiz import QuizGenerateRequest
from app.prompts.quiz_prompt import RESEARCH_PROMPT_WITH_KB
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
    parsed = QuizOutputSchema(title="RAG 入门", summary="基础", questions=[_question()])
    return {"raw": object(), "parsed": parsed, "parsing_error": None}


def _kb_artifact(doc_id="doc_1", score=0.8):
    return {
        "results": [
            {
                "doc_id": doc_id,
                "doc_name": "内部资料.pdf",
                "chunk_index": 0,
                "page": 2,
                "snippet": "知识库事实片段",
                "score": score,
            }
        ]
    }


def _research_result(
    kb_doc_id="doc_1", with_kb=True, brief="【解读】按文档出题", kb_score=0.8
):
    messages = [HumanMessage(content="研究一下")]
    if with_kb:
        messages.append(
            ToolMessage(
                content="知识库摘要",
                tool_call_id="1",
                name="search_knowledge_base",
                artifact=_kb_artifact(kb_doc_id, kb_score),
            )
        )
    messages.append(AIMessage(content=brief))
    return {"messages": messages}


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


def _request(**kw):
    values = {"user_input": "请根据我的文档生成闯关题目", "use_knowledge_base": True, "document_id": "doc_1"}
    values.update(kw)
    return QuizGenerateRequest(**values)


KB_TOOL = SimpleNamespace(name="search_knowledge_base")


def _patch_builders(monkeypatch, agents):
    captured: list[dict] = []
    queue = list(agents)

    def fake_build_agent(llm, tools=None, system_prompt=None):
        captured.append({"tools": list(tools or []), "prompt": system_prompt})
        return queue.pop(0)

    monkeypatch.setattr(quiz_service, "build_research_agent", fake_build_agent)
    monkeypatch.setattr(
        quiz_service,
        "build_search_tools",
        lambda settings=None: (_ for _ in ()).throw(AssertionError("不应装配联网工具")),
    )
    monkeypatch.setattr(
        quiz_service, "build_knowledge_base_tool", lambda scope, settings=None: KB_TOOL
    )
    monkeypatch.setattr(quiz_service, "build_chat_model", lambda *a, **kw: object())
    return captured


def test_document_mode_uses_only_kb_tool(monkeypatch):
    captured = _patch_builders(monkeypatch, [FakeAgent(result=_research_result())])

    quiz = generate_quiz(
        _request(),
        knowledge_scope=KnowledgeScope(user_id=7, document_ids=["doc_1"]),
        grounded_chain=FakeChain([_ok()]),
    )

    assert [tool.name for tool in captured[0]["tools"]] == ["search_knowledge_base"]
    assert captured[0]["prompt"] == RESEARCH_PROMPT_WITH_KB
    assert quiz.grounded is True
    assert quiz.sources[0].doc_id == "doc_1"


def test_document_mode_keeps_low_score_kb_sources(monkeypatch):
    _patch_builders(
        monkeypatch,
        [FakeAgent(result=_research_result(kb_score=0.33))],
    )

    quiz = generate_quiz(
        _request(),
        knowledge_scope=KnowledgeScope(user_id=7, document_ids=["doc_1"]),
        grounded_chain=FakeChain([_ok()]),
    )

    assert quiz.sources[0].kind == "knowledge_base"
    assert quiz.sources[0].score == 0.33


def test_document_mode_falls_back_when_no_kb_sources(monkeypatch):
    _patch_builders(
        monkeypatch,
        [FakeAgent(result=_research_result(with_kb=False, brief="【解读】泛化内容"))],
    )
    chain = FakeChain([_ok()])

    quiz = generate_quiz(
        _request(),
        chain=chain,
        knowledge_scope=KnowledgeScope(user_id=7, document_ids=["doc_1"]),
        grounded_chain=FakeChain([_ok()]),
    )

    assert quiz.grounded is False
    assert quiz.sources == []
    assert chain.calls == 1


def test_document_mode_falls_back_when_agent_errors(monkeypatch):
    _patch_builders(monkeypatch, [FakeAgent(exc=RuntimeError("agent down"))])
    chain = FakeChain([_ok()])

    quiz = generate_quiz(
        _request(),
        chain=chain,
        knowledge_scope=KnowledgeScope(user_id=7, document_ids=["doc_1"]),
        grounded_chain=FakeChain([_ok()]),
    )

    assert quiz.grounded is False
    assert quiz.sources == []
    assert chain.calls == 1


def test_document_mode_falls_back_when_source_from_other_document(monkeypatch):
    _patch_builders(
        monkeypatch, [FakeAgent(result=_research_result(kb_doc_id="doc_other"))]
    )
    chain = FakeChain([_ok()])

    quiz = generate_quiz(
        _request(),
        chain=chain,
        knowledge_scope=KnowledgeScope(user_id=7, document_ids=["doc_1"]),
        grounded_chain=FakeChain([_ok()]),
    )

    assert quiz.grounded is False
    assert quiz.sources == []
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


def test_document_mode_falls_back_when_kb_tool_build_fails(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("chroma unavailable")

    monkeypatch.setattr(quiz_service, "build_knowledge_base_tool", boom)
    chain = FakeChain([_ok()])

    quiz = generate_quiz(
        _request(),
        chain=chain,
        knowledge_scope=KnowledgeScope(user_id=7, document_ids=["doc_1"]),
        grounded_chain=FakeChain([_ok()]),
    )

    assert quiz.grounded is False
    assert quiz.sources == []
    assert chain.calls == 1


def test_knowledge_mode_requires_scope():
    with pytest.raises(ValidationError):
        generate_quiz(_request(), chain=FakeChain([_ok()]))
