from typing import Any, Optional

from app.core.config import get_settings
from app.core.exceptions import QuizGenerationError, ValidationError
from app.core.logging import get_logger
from app.llm.langchain_factory import build_chat_model
from app.llm.quiz_chain import build_quiz_chain
from app.models.quiz import Option, Question, Quiz, QuizGenerateRequest
from app.utils.content_filter import assert_safe
from app.utils.id_generator import generate_quiz_id
from app.utils.text_cleaner import clean_user_input

logger = get_logger("quiz_service")

_DIFFICULTY_INSTRUCTIONS = {
    "easy": "整体偏简单，适合入门者建立信心。",
    "medium": "中等难度，兼顾理解与辨析。",
    "hard": "偏难，重点考察细节、边界与易错点。",
    "mixed": "难易混合，覆盖基础概念到进阶应用。",
}


def _unwrap(result: Any) -> tuple[Any, Optional[Exception]]:
    """兼容 include_raw=True 的 {raw, parsed, parsing_error} 与直接返回 parsed 两种形态。"""
    if isinstance(result, dict) and "parsed" in result:
        return result.get("parsed"), result.get("parsing_error")
    return result, None


def _validate_question(raw: Any, index: int) -> Question:
    """三级校验：字段完整性 + 答案与选项一致性 + 题型答案数量。"""
    if not raw.stem or not raw.options or not raw.answer:
        raise QuizGenerationError(f"第 {index + 1} 题字段不完整")
    if len(raw.options) < 2:
        raise QuizGenerationError(f"第 {index + 1} 题选项少于 2 个")

    option_keys = [opt.key for opt in raw.options]
    if len(set(option_keys)) != len(option_keys):
        raise QuizGenerationError(f"第 {index + 1} 题选项 key 重复")

    unique_answer = set(raw.answer)
    if not unique_answer.issubset(set(option_keys)):
        raise QuizGenerationError(f"第 {index + 1} 题答案与选项不匹配")

    if raw.type in ("single", "judge") and len(unique_answer) != 1:
        raise QuizGenerationError(f"第 {index + 1} 题（{raw.type}）答案数量应为 1")
    if raw.type == "multiple" and len(unique_answer) < 2:
        raise QuizGenerationError(f"第 {index + 1} 题（multiple）答案应不少于 2 个")

    return Question(
        id=raw.id or f"q{index + 1}",
        type=raw.type,
        stem=raw.stem,
        options=[Option(key=opt.key, text=opt.text) for opt in raw.options],
        answer=sorted(unique_answer),
        explanation=raw.explanation,
        knowledge_point=raw.knowledge_point,
        difficulty=raw.difficulty,
    )


def _build_quiz(parsed: Any, cleaned_input: str) -> Quiz:
    if parsed is None:
        raise QuizGenerationError("模型未返回结构化结果")
    questions = [_validate_question(q, i) for i, q in enumerate(parsed.questions)]
    if not questions:
        raise QuizGenerationError("未生成任何题目")
    return Quiz(
        quiz_id=generate_quiz_id(),
        title=(parsed.title or "学习闯关").strip(),
        summary=(parsed.summary or "").strip(),
        source_type="text",
        user_input=cleaned_input,
        questions=questions,
    )


def generate_quiz(request: QuizGenerateRequest, chain: Optional[Any] = None) -> Quiz:
    """出题主流程：清洗 -> 敏感词 -> 调用链 -> 校验 -> 失败重试 -> 兜底异常。

    chain 可注入（用于测试）；为 None 时用真实 LangChain 链。
    """
    cleaned = clean_user_input(request.user_input)
    if not cleaned:
        raise ValidationError("学习内容不能为空")
    assert_safe(cleaned)

    settings = get_settings()
    if chain is None:
        llm = build_chat_model(settings.quiz_temperature, settings.quiz_max_tokens)
        chain = build_quiz_chain(llm)

    payload = {
        "question_count": request.question_count,
        "difficulty_instruction": _DIFFICULTY_INSTRUCTIONS.get(
            request.difficulty, _DIFFICULTY_INSTRUCTIONS["mixed"]
        ),
        "user_input": cleaned,
    }

    attempts = settings.llm_max_retries + 1
    last_error: Optional[Exception] = None
    for attempt in range(attempts):
        try:
            result = chain.invoke(payload)
            parsed, parsing_error = _unwrap(result)
            if parsing_error is not None:
                raise parsing_error
            quiz = _build_quiz(parsed, cleaned)
            if len(quiz.questions) != request.question_count:
                logger.info(
                    "quiz_count_mismatch",
                    expected=request.question_count,
                    actual=len(quiz.questions),
                )
            if attempt > 0:
                logger.info("quiz_generation_recovered", attempt=attempt)
            return quiz
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning("quiz_generation_attempt_failed", attempt=attempt, error=str(exc))

    logger.error("quiz_generation_failed", error=str(last_error))
    raise QuizGenerationError()
