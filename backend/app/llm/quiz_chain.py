from langchain_core.runnables import Runnable

from app.llm.output_schemas import QuizOutputSchema
from app.prompts.quiz_prompt import (
    QUIZ_GROUNDED_PROMPT,
    QUIZ_PROMPT_V1,
    QUIZ_V2_SCHEMA_EXAMPLE,
    SCHEMA_EXAMPLE,
)


def build_quiz_chain(llm) -> Runnable:
    """未接地出题链：prompt | with_structured_output(json_mode, include_raw=True)。

    返回的 Runnable invoke 后得到 {"raw", "parsed", "parsing_error"}。
    """
    structured_llm = llm.with_structured_output(
        QuizOutputSchema, method="json_mode", include_raw=True
    )
    prompt = QUIZ_PROMPT_V1.partial(schema_example=SCHEMA_EXAMPLE)
    return prompt | structured_llm


def build_grounded_chain(llm) -> Runnable:
    """接地出题链（两阶段之阶段二）：研究简报 + 用户内容 -> json_mode 结构化题库（含 interpretation）。

    DeepSeek 的 json_mode 结构化输出稳定可靠（v1 已验证），故出题结构化统一走此链，
    而不依赖 Agent 的工具调用式结构化输出。
    """
    structured_llm = llm.with_structured_output(
        QuizOutputSchema, method="json_mode", include_raw=True
    )
    prompt = QUIZ_GROUNDED_PROMPT.partial(schema_example=QUIZ_V2_SCHEMA_EXAMPLE)
    return prompt | structured_llm
