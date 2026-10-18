import json

from app.prompts.quiz_prompt import QUIZ_PROMPT_V1, SCHEMA_EXAMPLE


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
