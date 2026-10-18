import json

from app.prompts.report_prompt import REPORT_PROMPT_V1, REPORT_SCHEMA_EXAMPLE


def test_input_variables():
    assert set(REPORT_PROMPT_V1.input_variables) == {
        "topic",
        "score_summary",
        "quiz_json",
        "answer_records",
        "schema_example",
    }


def test_renders_with_json_instruction():
    messages = REPORT_PROMPT_V1.format_messages(
        topic="RAG",
        score_summary='{"accuracy": 100}',
        quiz_json="[]",
        answer_records="[]",
        schema_example=REPORT_SCHEMA_EXAMPLE,
    )
    assert len(messages) == 2
    content = messages[1].content
    assert "JSON" in content
    assert "RAG" in content


def test_schema_example_valid_json():
    data = json.loads(REPORT_SCHEMA_EXAMPLE)
    assert data["accuracy"] == 80
    assert len(data["three_line_summary"]) == 3
    assert "share_quote" in data
