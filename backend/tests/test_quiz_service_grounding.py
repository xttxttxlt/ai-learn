"""两阶段接地出题服务单测：研究 Agent + json_mode 结构化链；覆盖成功、来源映射与各类降级。"""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.llm.output_schemas import OptionSchema, QuestionSchema, QuizOutputSchema
from app.models.quiz import QuizGenerateRequest
from app.services.quiz_service import generate_quiz


def _question(qid="q1", qtype="single", answer=None):
    return QuestionSchema(
        id=qid,
        type=qtype,
        stem="Harness Engineering 指什么？",
        options=[OptionSchema(key="A", text="围绕 AI 智能体的工程实践"), OptionSchema(key="B", text="马具")],
        answer=answer or ["A"],
        explanation="指围绕模型构建工具/控制/上下文的工程实践",
        knowledge_point="Harness 定义",
        difficulty="easy",
    )


def _parsed(interpretation=""):
    return QuizOutputSchema(
        title="Harness Engineering",
        summary="AI 智能体工程",
        interpretation=interpretation,
        questions=[_question()],
    )


def _ok(parsed=None):
    return {"raw": object(), "parsed": parsed if parsed is not None else _parsed(), "parsing_error": None}


def _request(**kw):
    return QuizGenerateRequest(user_input=kw.pop("user_input", "Harness Engineering"), **kw)


def _research_result(brief="【解读】按 AI 智能体工程领域\n【关键事实】见 http://faros"):
    return {
        "messages": [
            HumanMessage(content="研究一下"),
            ToolMessage(
                content="搜索摘要",
                tool_call_id="1",
                name="web_search_brief",
                artifact={"results": [{"title": "Faros", "url": "http://faros", "score": 0.94}]},
            ),
            ToolMessage(
                content="抽取正文",
                tool_call_id="2",
                name="web_extract",
                artifact={"results": [{"title": "Port", "url": "http://port"}]},
            ),
            AIMessage(content=brief),
        ]
    }


class FakeAgent:
    def __init__(self, result=None, exc=None):
        self.result = result
        self.exc = exc
        self.calls = 0
        self.last_config = None

    def invoke(self, payload, config=None):
        self.calls += 1
        self.last_config = config
        if self.exc:
            raise self.exc
        return self.result


class FakeChain:
    """既可用于未接地 chain，也可用于阶段二 grounded_chain（同 _unwrap 形态）。"""

    def __init__(self, results):
        self.results = list(results)
        self.calls = 0
        self.last_payload = None

    def invoke(self, payload):
        self.last_payload = payload
        item = self.results[min(self.calls, len(self.results) - 1)]
        self.calls += 1
        if isinstance(item, Exception):
            raise item
        return item


def test_grounded_success_maps_fields_and_sources():
    agent = FakeAgent(result=_research_result())
    gchain = FakeChain([_ok(_parsed(interpretation="按 AI 智能体工程领域出题"))])
    quiz = generate_quiz(_request(), agent=agent, grounded_chain=gchain)
    assert quiz.grounded is True
    assert quiz.interpretation == "按 AI 智能体工程领域出题"
    assert agent.calls == 1
    assert isinstance(agent.last_config, dict) and "recursion_limit" in agent.last_config
    # extract 优先，其次 search（按 score）
    assert [s.url for s in quiz.sources] == ["http://port", "http://faros"]
    assert quiz.sources[0].kind == "extract"
    # 研究简报被注入阶段二 payload
    assert "AI 智能体工程领域" in gchain.last_payload["research"]
    assert gchain.last_payload["user_input"] == "Harness Engineering"


def test_grounded_falls_back_on_agent_error():
    agent = FakeAgent(exc=RuntimeError("tavily down"))
    chain = FakeChain([_ok()])
    quiz = generate_quiz(_request(), chain=chain, agent=agent)
    assert agent.calls == 1
    assert chain.calls == 1
    assert quiz.grounded is False
    assert quiz.sources == []


def test_grounded_falls_back_when_no_research_and_no_sources():
    agent = FakeAgent(result={"messages": [HumanMessage(content="x")]})
    chain = FakeChain([_ok()])
    quiz = generate_quiz(_request(), chain=chain, agent=agent)
    assert quiz.grounded is False
    assert chain.calls == 1


def test_grounded_falls_back_when_phase2_keeps_failing():
    agent = FakeAgent(result=_research_result())
    gchain = FakeChain([{"raw": object(), "parsed": None, "parsing_error": ValueError("bad json")}])
    chain = FakeChain([_ok()])
    quiz = generate_quiz(_request(), chain=chain, agent=agent, grounded_chain=gchain)
    assert gchain.calls == 3  # llm_max_retries(2) + 1
    assert chain.calls == 1  # 降级到未接地
    assert quiz.grounded is False


def test_grounded_invalid_questions_fall_back():
    agent = FakeAgent(result=_research_result())
    gchain = FakeChain([_ok(_parsed())])  # 正常
    # 让阶段二产出答案与选项不匹配的题目 -> _build_quiz 抛错 -> 降级
    bad = QuizOutputSchema(title="t", summary="s", interpretation="", questions=[_question(answer=["Z"])])
    gchain.results = [{"raw": object(), "parsed": bad, "parsing_error": None}]
    chain = FakeChain([_ok()])
    quiz = generate_quiz(_request(), chain=chain, agent=agent, grounded_chain=gchain)
    assert quiz.grounded is False
    assert chain.calls == 1


def test_chain_injection_uses_plain_path_only():
    chain = FakeChain([_ok()])
    quiz = generate_quiz(_request(), chain=chain)
    assert chain.calls == 1
    assert quiz.grounded is False
    assert quiz.sources == []
