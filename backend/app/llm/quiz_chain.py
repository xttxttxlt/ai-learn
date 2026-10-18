from langchain_core.runnables import Runnable

from app.llm.output_schemas import QuizOutputSchema
from app.prompts.quiz_prompt import QUIZ_PROMPT_V1, SCHEMA_EXAMPLE


def build_quiz_chain(llm) -> Runnable:
    """prompt | with_structured_output(json_mode, include_raw=True)。

    返回的 Runnable invoke 后得到 {"raw", "parsed", "parsing_error"}。
    """
    structured_llm = llm.with_structured_output(
        QuizOutputSchema, method="json_mode", include_raw=True
    )
    prompt = QUIZ_PROMPT_V1.partial(schema_example=SCHEMA_EXAMPLE)
    return prompt | structured_llm
