from langchain_core.messages import AIMessage, HumanMessage

from app.core.config import Settings
from app.llm.output_schemas import OptionSchema, QuestionSchema, QuizOutputSchema
from app.models.quiz import QuizGenerateRequest
from app.services import quiz_service
from app.services.quiz_service import generate_quiz


def _settings(**kwargs):
    values = {"deepseek_api_key": "test-key", "tavily_api_key": "tvly-test", "enable_web_search": True}
    values.update(kwargs)
    return Settings(_env_file=None, **values)


def _ok():
    parsed = QuizOutputSchema(
        title="RAG 入门",
        summary="基础",
        questions=[
            QuestionSchema(
                id="q1",
                type="single",
                stem="RAG 是什么？",
                options=[OptionSchema(key="A", text="检索增强生成"), OptionSchema(key="B", text="数据库")],
                answer=["A"],
                explanation="讲解",
                knowledge_point="RAG",
                difficulty="easy",
            )
        ],
    )
    return {"raw": object(), "parsed": parsed, "parsing_error": None}


class FakeChain:
    def __init__(self, result=None, exc=None):
        self.result = result or _ok()
        self.exc = exc
        self.calls = 0

    def invoke(self, payload):
        self.calls += 1
        if self.exc:
            raise self.exc
        return self.result


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


def test_all_off_uses_plain_chain_without_building_agents(monkeypatch):
    monkeypatch.setattr(quiz_service, "get_settings", lambda: _settings())

    def boom(*args, **kwargs):
        raise AssertionError("不应构建 Agent 或联网工具")

    monkeypatch.setattr(quiz_service, "build_research_agent", boom)
    monkeypatch.setattr(quiz_service, "build_search_tools", boom)
    chain = FakeChain()

    quiz = generate_quiz(QuizGenerateRequest(user_input="RAG"), chain=chain)

    assert chain.calls == 1
    assert quiz.grounded is False
    assert quiz.sources == []


def test_web_request_without_capability_falls_back_plain(monkeypatch):
    monkeypatch.setattr(
        quiz_service,
        "get_settings",
        lambda: _settings(tavily_api_key="", enable_web_search=False),
    )

    def boom(*args, **kwargs):
        raise AssertionError("联网能力不可用时不应构建 Agent")

    monkeypatch.setattr(quiz_service, "build_research_agent", boom)
    monkeypatch.setattr(quiz_service, "build_search_tools", boom)
    chain = FakeChain()

    quiz = generate_quiz(
        QuizGenerateRequest(user_input="RAG", use_web_search=True), chain=chain
    )

    assert chain.calls == 1
    assert quiz.grounded is False


def test_web_request_uses_grounded_agent(monkeypatch):
    monkeypatch.setattr(quiz_service, "get_settings", lambda: _settings())
    agent = FakeAgent(
        result={
            "messages": [
                HumanMessage(content="研究"),
                AIMessage(content="【解读】联网结果"),
            ]
        }
    )
    captured: dict = {}

    def fake_build_agent(llm, tools=None, system_prompt=None):
        captured["tools"] = list(tools or [])
        captured["prompt"] = system_prompt
        return agent

    monkeypatch.setattr(quiz_service, "build_research_agent", fake_build_agent)
    monkeypatch.setattr(
        quiz_service,
        "build_search_tools",
        lambda settings=None: [object(), object(), object()],
    )
    monkeypatch.setattr(quiz_service, "build_chat_model", lambda *a, **kw: object())
    grounded_chain = FakeChain()

    quiz = generate_quiz(
        QuizGenerateRequest(user_input="RAG", use_web_search=True),
        grounded_chain=grounded_chain,
    )

    assert agent.calls == 1
    assert len(captured["tools"]) == 3
    assert grounded_chain.calls == 1
    assert quiz.grounded is True
