from langchain_core.runnables import Runnable

from app.llm.output_schemas import ReportOutputSchema
from app.prompts.report_prompt import REPORT_PROMPT_V1, REPORT_SCHEMA_EXAMPLE


def build_report_chain(llm) -> Runnable:
    """prompt | with_structured_output(json_mode, include_raw=True)。"""
    structured_llm = llm.with_structured_output(
        ReportOutputSchema, method="json_mode", include_raw=True
    )
    prompt = REPORT_PROMPT_V1.partial(schema_example=REPORT_SCHEMA_EXAMPLE)
    return prompt | structured_llm
