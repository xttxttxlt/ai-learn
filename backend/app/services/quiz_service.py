from typing import Any, Optional

from app.core.config import get_settings
from app.core.exceptions import QuizGenerationError, ValidationError
from app.core.logging import get_logger
from app.llm.langchain_factory import build_chat_model
from app.llm.knowledge_base import KnowledgeScope, build_knowledge_base_tool
from app.llm.quiz_agent import (
    build_research_agent,
    extract_research_text,
    extract_sources_from_messages,
)
from app.llm.quiz_chain import build_grounded_chain, build_quiz_chain
from app.llm.search_tools import build_search_tools
from app.models.quiz import Option, Question, Quiz, QuizGenerateRequest, Source
from app.prompts.quiz_prompt import (
    RESEARCH_PROMPT_V2,
    RESEARCH_PROMPT_WITH_KB,
    format_research_user_message,
)
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

DOCUMENT_UNAVAILABLE_MESSAGE = "文档内容不可用，请重新上传"
DOCUMENT_QUIZ_FAILED_MESSAGE = "文档出题失败，请稍后重试"


def _grounding_enabled(settings) -> bool:
    """仅当开启联网开关且配置了 Tavily key 时才走接地出题。"""
    return bool(settings.enable_web_search and settings.tavily_api_key)


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


def _build_quiz(
    parsed: Any,
    cleaned_input: str,
    sources: Optional[list[Source]] = None,
    grounded: bool = False,
) -> Quiz:
    if parsed is None:
        raise QuizGenerationError("模型未返回结构化结果")
    questions = [_validate_question(q, i) for i, q in enumerate(parsed.questions)]
    if not questions:
        raise QuizGenerationError("未生成任何题目")
    return Quiz(
        quiz_id=generate_quiz_id(),
        title=(parsed.title or "学习闯关").strip(),
        summary=(parsed.summary or "").strip(),
        interpretation=(getattr(parsed, "interpretation", "") or "").strip(),
        source_type="text",
        user_input=cleaned_input,
        questions=questions,
        sources=sources or [],
        grounded=grounded,
    )


def _generate_grounded(
    request: QuizGenerateRequest,
    cleaned: str,
    settings,
    difficulty_instruction: str,
    agent: Optional[Any] = None,
    grounded_chain: Optional[Any] = None,
    kb_min_score: Optional[float] = None,
) -> Quiz:
    """接地出题（两阶段）：研究 Agent 联网检索/抽取出简报与来源 -> json_mode 链产出结构化题库。"""
    # 阶段一：研究（Agent 自主选择 web_search_brief/full、web_extract）
    if agent is None:
        llm = build_chat_model(settings.quiz_temperature, settings.quiz_max_tokens)
        agent = build_research_agent(llm, build_search_tools(settings))

    research_msg = format_research_user_message(cleaned)
    result = agent.invoke(
        {"messages": [{"role": "user", "content": research_msg}]},
        config={"recursion_limit": settings.quiz_agent_recursion_limit},
    )
    messages = result.get("messages") if isinstance(result, dict) else None
    research = extract_research_text(messages)
    sources = [Source(**s) for s in extract_sources_from_messages(messages)]
    if kb_min_score is not None:
        sources = [
            source
            for source in sources
            if not (
                source.kind == "knowledge_base"
                and (source.score is None or source.score < kb_min_score)
            )
        ]
    if not research.strip() and not sources:
        raise QuizGenerationError("接地未取得有效检索信息")

    # 阶段二：结构化出题（复用 json_mode，带重试兜底；DeepSeek 下稳定）
    if grounded_chain is None:
        grounded_chain = build_grounded_chain(
            build_chat_model(settings.quiz_temperature, settings.quiz_max_tokens)
        )
    payload = {
        "question_count": request.question_count,
        "difficulty_instruction": difficulty_instruction,
        "research": research,
        "user_input": cleaned,
    }
    attempts = settings.llm_max_retries + 1
    last_error: Optional[Exception] = None
    for attempt in range(attempts):
        try:
            res = grounded_chain.invoke(payload)
            parsed, parsing_error = _unwrap(res)
            if parsing_error is not None:
                raise parsing_error
            quiz = _build_quiz(parsed, cleaned, sources=sources, grounded=True)
            if len(quiz.questions) != request.question_count:
                logger.info(
                    "quiz_count_mismatch",
                    expected=request.question_count,
                    actual=len(quiz.questions),
                    path="grounded",
                )
            return quiz
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning("grounded_gen_attempt_failed", attempt=attempt, error=str(exc))
    raise QuizGenerationError("接地出题失败") from last_error


def _generate_plain(
    request: QuizGenerateRequest,
    cleaned: str,
    settings,
    difficulty_instruction: str,
    chain: Optional[Any] = None,
) -> Quiz:
    """未接地出题（v1 链）：清洗后的文本直接进模型，带重试与兜底。"""
    if chain is None:
        llm = build_chat_model(settings.quiz_temperature, settings.quiz_max_tokens)
        chain = build_quiz_chain(llm)

    payload = {
        "question_count": request.question_count,
        "difficulty_instruction": difficulty_instruction,
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


def _has_scoped_kb_source(quiz: Quiz, scope: KnowledgeScope) -> bool:
    scope_ids = set(scope.document_ids)
    return any(
        source.kind == "knowledge_base" and source.doc_id in scope_ids
        for source in quiz.sources
    )


def _generate_document_quiz(
    request: QuizGenerateRequest,
    cleaned: str,
    settings,
    difficulty_instruction: str,
    scope: KnowledgeScope,
    agent: Optional[Any],
    grounded_chain: Optional[Any],
    kb_tool: Optional[Any],
) -> Quiz:
    """文档一键闯关：仅提供知识库工具，不联网；无文档来源即失败。"""
    if kb_tool is None:
        try:
            kb_tool = build_knowledge_base_tool(scope, settings)
        except Exception as exc:  # noqa: BLE001
            logger.warning("knowledge_tool_build_failed", error=str(exc))
            raise QuizGenerationError(DOCUMENT_UNAVAILABLE_MESSAGE) from exc

    if agent is None:
        llm = build_chat_model(settings.quiz_temperature, settings.quiz_max_tokens)
        agent = build_research_agent(
            llm, [kb_tool], system_prompt=RESEARCH_PROMPT_WITH_KB
        )

    try:
        quiz = _generate_grounded(
            request,
            cleaned,
            settings,
            difficulty_instruction,
            agent=agent,
            grounded_chain=grounded_chain,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("document_quiz_failed", error=str(exc))
        raise QuizGenerationError(DOCUMENT_QUIZ_FAILED_MESSAGE) from exc

    if not _has_scoped_kb_source(quiz, scope):
        logger.warning("document_quiz_without_kb_source")
        raise QuizGenerationError(DOCUMENT_UNAVAILABLE_MESSAGE)
    return quiz


def _generate_home_quiz_with_knowledge(
    request: QuizGenerateRequest,
    cleaned: str,
    settings,
    difficulty_instruction: str,
    scope: KnowledgeScope,
    chain: Optional[Any],
    agent: Optional[Any],
    grounded_chain: Optional[Any],
    kb_tool: Optional[Any],
) -> Quiz:
    """首页出题：知识库 + 联网自主路由；失败依次降级到仅联网、未接地。"""
    tools: list[Any] = []
    if kb_tool is None:
        try:
            kb_tool = build_knowledge_base_tool(scope, settings)
        except Exception as exc:  # noqa: BLE001
            logger.warning("knowledge_tool_build_failed", error=str(exc))
            kb_tool = None
    if kb_tool is not None:
        tools.append(kb_tool)
    if _grounding_enabled(settings):
        tools.extend(build_search_tools(settings))

    if not tools:
        return _generate_plain(
            request, cleaned, settings, difficulty_instruction, chain=chain
        )

    grounded_agent = agent
    if grounded_agent is None:
        llm = build_chat_model(settings.quiz_temperature, settings.quiz_max_tokens)
        grounded_agent = build_research_agent(
            llm, tools, system_prompt=RESEARCH_PROMPT_WITH_KB
        )

    try:
        return _generate_grounded(
            request,
            cleaned,
            settings,
            difficulty_instruction,
            agent=grounded_agent,
            grounded_chain=grounded_chain,
            kb_min_score=settings.kb_min_relevance_score,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("knowledge_quiz_fallback", error=str(exc))

    # 注入 agent 的场景（测试或调用方自带 Agent）不再重建联网 Agent。
    if agent is None and _grounding_enabled(settings):
        try:
            web_agent = build_research_agent(
                build_chat_model(settings.quiz_temperature, settings.quiz_max_tokens),
                build_search_tools(settings),
                system_prompt=RESEARCH_PROMPT_V2,
            )
            return _generate_grounded(
                request,
                cleaned,
                settings,
                difficulty_instruction,
                agent=web_agent,
                grounded_chain=grounded_chain,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("web_quiz_fallback", error=str(exc))

    return _generate_plain(
        request, cleaned, settings, difficulty_instruction, chain=chain
    )


def generate_quiz(
    request: QuizGenerateRequest,
    chain: Optional[Any] = None,
    agent: Optional[Any] = None,
    grounded_chain: Optional[Any] = None,
    knowledge_scope: Optional[KnowledgeScope] = None,
    kb_tool: Optional[Any] = None,
) -> Quiz:
    """出题主流程：清洗 -> 敏感词 -> 优先接地 -> 失败降级到未接地链。

    chain / agent / grounded_chain 均可注入（用于测试）：
    - 注入 chain：走未接地 v1 路径；
    - 注入 agent（+可选 grounded_chain）：走两阶段接地路径（失败再降级到 chain/真实 v1 链）；
    - 都不注入：按配置 enable_web_search + tavily_api_key 决定是否接地。
    knowledge_scope 非空时启用个人知识库：
    - document_ids 非空：文档一键闯关，仅知识库工具、不联网、无来源即失败；
    - document_ids 为空：首页出题，知识库 + 联网自主路由，失败逐级降级。
    """
    cleaned = clean_user_input(request.user_input)
    if not cleaned:
        raise ValidationError("学习内容不能为空")
    assert_safe(cleaned)

    settings = get_settings()
    difficulty_instruction = _DIFFICULTY_INSTRUCTIONS.get(
        request.difficulty, _DIFFICULTY_INSTRUCTIONS["mixed"]
    )

    if knowledge_scope is not None:
        if knowledge_scope.is_document_scope:
            return _generate_document_quiz(
                request,
                cleaned,
                settings,
                difficulty_instruction,
                knowledge_scope,
                agent,
                grounded_chain,
                kb_tool,
            )
        return _generate_home_quiz_with_knowledge(
            request,
            cleaned,
            settings,
            difficulty_instruction,
            knowledge_scope,
            chain,
            agent,
            grounded_chain,
            kb_tool,
        )

    use_grounding = (agent is not None) or (chain is None and _grounding_enabled(settings))
    if use_grounding:
        try:
            return _generate_grounded(
                request,
                cleaned,
                settings,
                difficulty_instruction,
                agent=agent,
                grounded_chain=grounded_chain,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("grounded_quiz_fallback", error=str(exc))

    return _generate_plain(request, cleaned, settings, difficulty_instruction, chain=chain)
