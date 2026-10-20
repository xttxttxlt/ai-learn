import json

from app.llm.output_schemas import QuizOutputSchema
from app.prompts.quiz_prompt import (
    QUIZ_GROUNDED_PROMPT,
    QUIZ_PROMPT_V1,
    QUIZ_V2_SCHEMA_EXAMPLE,
    RESEARCH_PROMPT_V2,
    RESEARCH_PROMPT_WITH_KB,
    SCHEMA_EXAMPLE,
    format_research_user_message,
)


def test_prompt_has_expected_input_variables():
    assert set(QUIZ_PROMPT_V1.input_variables) == {
        "question_count",
        "difficulty_instruction",
        "schema_example",
        "user_input",
    }


def test_prompt_renders_with_json_instruction_and_user_input():
    messages = QUIZ_PROMPT_V1.format_messages(
        question_count=5,
        difficulty_instruction="难易混合",
        schema_example=SCHEMA_EXAMPLE,
        user_input="什么是 RAG",
    )
    assert len(messages) == 2  # system + user
    user_content = messages[1].content
    # json_mode 要求 prompt 内含明确 JSON 指令与结构示例
    assert "JSON" in user_content
    assert "什么是 RAG" in user_content
    assert '"questions"' in user_content
    assert "5" in user_content


def test_schema_example_is_valid_json():
    data = json.loads(SCHEMA_EXAMPLE)
    assert data["questions"][0]["type"] == "single"
    assert data["questions"][0]["options"][0]["key"] == "A"


def test_research_prompt_is_string_and_describes_tools():
    assert isinstance(RESEARCH_PROMPT_V2, str)
    for token in ("web_search_brief", "web_search_full", "web_extract"):
        assert token in RESEARCH_PROMPT_V2
    # 要求产出研究简报（含解读/关键事实/接地情况）
    assert "研究简报" in RESEARCH_PROMPT_V2
    assert "解读" in RESEARCH_PROMPT_V2


def test_grounded_prompt_variables_and_interpretation():
    assert set(QUIZ_GROUNDED_PROMPT.input_variables) == {
        "question_count",
        "difficulty_instruction",
        "schema_example",
        "research",
        "user_input",
    }
    messages = QUIZ_GROUNDED_PROMPT.format_messages(
        question_count=5,
        difficulty_instruction="难易混合",
        schema_example=QUIZ_V2_SCHEMA_EXAMPLE,
        research="【解读】按 AI 智能体工程领域",
        user_input="Harness Engineering",
    )
    user_content = messages[1].content
    assert "interpretation" in user_content
    assert "研究简报" in user_content
    assert "Harness Engineering" in user_content
    # json_mode 需要明确 JSON 指令
    assert "JSON" in user_content


def test_v2_schema_example_is_valid_json():
    data = json.loads(QUIZ_V2_SCHEMA_EXAMPLE)
    assert "interpretation" in data
    assert data["questions"][0]["type"] == "single"


def test_research_user_message_formatter():
    msg = format_research_user_message("什么是 Harness Engineering")
    assert "Harness Engineering" in msg


def test_research_prompt_with_kb_contract():
    assert isinstance(RESEARCH_PROMPT_WITH_KB, str)
    for token in (
        "search_knowledge_base",
        "web_search_brief",
        "web_search_full",
        "web_extract",
    ):
        assert token in RESEARCH_PROMPT_WITH_KB
    assert "个人知识库" in RESEARCH_PROMPT_WITH_KB
    assert "当前文档" in RESEARCH_PROMPT_WITH_KB
    assert "不得编造" in RESEARCH_PROMPT_WITH_KB
    assert "10 次" in RESEARCH_PROMPT_WITH_KB
    assert "联网" in RESEARCH_PROMPT_WITH_KB


def test_grounded_prompt_mentions_knowledge_base_sources():
    assert "个人知识库" in QUIZ_GROUNDED_PROMPT.messages[0].prompt.template
    assert "个人知识库" in QUIZ_GROUNDED_PROMPT.messages[1].prompt.template


def test_quiz_output_schema_interpretation_optional():
    # 不带 interpretation 也能构造（v1 降级链复用同一 schema）
    schema = QuizOutputSchema(title="t", summary="s", questions=[])
    assert schema.interpretation == ""
    schema2 = QuizOutputSchema(title="t", summary="s", interpretation="按 AI 领域", questions=[])
    assert schema2.interpretation == "按 AI 领域"
