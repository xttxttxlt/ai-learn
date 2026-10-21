"""题目配图：Prompt 构建、百炼同步生图、COS 转存与并发编排。"""

import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import Any, Callable, Optional

import httpx
from fastapi.concurrency import run_in_threadpool

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.models.quiz import Question, Quiz
from app.repositories import image_usage_repository
from app.services import cos_storage_service

logger = get_logger("image_generation_service")

DASHSCOPE_IMAGE_PATH = "/services/aigc/multimodal-generation/generation"
NEGATIVE_PROMPT = (
    "低分辨率，低画质，文字，字母，数字，单词，名称，标题，字幕，标签，"
    "题号，题目，答案，卡片，边框，海报，广告，电商主图，商品详情页，产品目录，"
    "包装，说明书，横幅，参数表，图标列表，表格，图标，页眉，页脚，分屏，拼贴，"
    "分栏，拼图，信息图，排版，乱码，Logo，水印，UI元素，构图混乱"
)
_PROMPT_TAIL = (
    "画面必须是一张完整的单张照片：不要拼贴、不要分屏、不要表格、不要图标、"
    "不要页眉页脚、不要边框、不要文字、不要字母、不要数字、不要标签、不要卡片、"
    "不要广告、不要产品目录、不要海报、不要UI。"
)

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_QUOTED_CJK_RE = re.compile(r"[“\"']([\u4e00-\u9fff][^”\"']{0,30})[”\"']")
_NON_VISUAL_ANSWERS = {"正确", "错误", "对", "错"}


def _visual_subject(question: Question) -> str:
    """选出适合画成实物主体的中文词，避免把英文答案渲染成商品文字。

    优先用中文答案（如“苹果”）；答案本身是英文时，优先取题干引号里的中文主体
    （如“微波炉”对应的英文是？），避免直接让模型画 "microwave oven"。
    """
    answer_keys = set(question.answer or [])
    answer_texts = [
        (option.text or "").strip()
        for option in question.options
        if option.key in answer_keys and (option.text or "").strip()
    ]
    for text in answer_texts:
        if text in _NON_VISUAL_ANSWERS:
            continue
        if _CJK_RE.search(text):
            return text[:60]

    match = _QUOTED_CJK_RE.search(question.stem or "")
    if match:
        return match.group(1).strip()[:60]

    for text in answer_texts:
        if text not in _NON_VISUAL_ANSWERS:
            return text[:60]
    return ""


def build_image_prompt(question: Question) -> str:
    knowledge = (question.knowledge_point or "").strip()[:60]
    subject = _visual_subject(question) or knowledge

    if subject:
        parts = [
            f"一张单张的真实照片，画面只有一个主体：{subject}。"
            "背景简洁自然，主体清晰，光线柔和，主体占画面主要位置。"
        ]
    else:
        parts = ["一张单张的真实照片，背景简洁自然，主体清晰，光线柔和。"]
    parts.append(_PROMPT_TAIL)
    return "".join(parts)


def _extract_image_url(payload: Any) -> str:
    try:
        content = payload["output"]["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return ""
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("image"):
                return str(part["image"])
    return ""


def _should_retry(status_code: int) -> bool:
    return status_code == 429 or 500 <= status_code < 600


def _retry_delay(settings: Settings, attempt: int) -> float:
    base = max(0.0, settings.image_retry_backoff_seconds) * (2**attempt)
    if base <= 0:
        return 0.0
    # 加抖动，避免并发的失败请求在同一时刻再次撞限流
    return base + random.uniform(0, min(1.0, base))


def generate_image_bytes(
    prompt: str,
    settings: Settings,
    client: Optional[httpx.Client] = None,
) -> Optional[bytes]:
    """调用百炼同步接口并下载图片；429/5xx 有界重试，最终失败返回 None。"""
    owns_client = client is None
    if client is None:
        client = httpx.Client(timeout=settings.image_timeout_seconds)

    url = f"{settings.image_base_url.rstrip('/')}{DASHSCOPE_IMAGE_PATH}"
    payload = {
        "model": settings.image_model,
        "input": {
            "messages": [
                {"role": "user", "content": [{"text": prompt}]}
            ]
        },
        "parameters": {
            "negative_prompt": NEGATIVE_PROMPT,
            "size": settings.image_size,
            "n": 1,
            "prompt_extend": False,
            "watermark": False,
        },
    }
    headers = {"Authorization": f"Bearer {settings.dashscope_api_key}"}

    attempts = max(1, settings.image_max_retries + 1)
    try:
        for attempt in range(attempts):
            try:
                response = client.post(url, headers=headers, json=payload)
            except httpx.TransportError as exc:
                if attempt < attempts - 1:
                    time.sleep(_retry_delay(settings, attempt))
                    continue
                logger.warning("image_generation_network_error", error=str(exc))
                return None

            if response.status_code != 200:
                if _should_retry(response.status_code) and attempt < attempts - 1:
                    logger.info(
                        "image_generation_retry",
                        status_code=response.status_code,
                        attempt=attempt + 1,
                    )
                    time.sleep(_retry_delay(settings, attempt))
                    continue
                logger.warning(
                    "image_generation_http_error", status_code=response.status_code
                )
                return None

            try:
                image_url = _extract_image_url(response.json())
            except ValueError:
                logger.warning("image_generation_invalid_json")
                return None
            if not image_url:
                logger.warning("image_generation_without_image")
                return None

            image_response = client.get(image_url)
            if image_response.status_code != 200 or not image_response.content:
                if _should_retry(image_response.status_code) and attempt < attempts - 1:
                    time.sleep(_retry_delay(settings, attempt))
                    continue
                logger.warning(
                    "image_download_failed", status_code=image_response.status_code
                )
                return None
            return image_response.content
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("image_generation_failed", error=str(exc))
        return None
    finally:
        if owns_client:
            client.close()


def _generate_batch(
    user_id: int,
    usage_date: date,
    quiz_id: str,
    items: list[tuple[int, Question]],
    settings: Settings,
    generator: Callable[[str, Settings], Optional[bytes]],
    uploader: Callable[[bytes, str, Settings], str],
) -> dict[int, str]:
    results: dict[int, str] = {}

    def work(index: int, question: Question) -> Optional[str]:
        prompt = build_image_prompt(question)
        data = generator(prompt, settings)
        if not data:
            return None
        key = cos_storage_service.build_object_key(
            user_id, usage_date, quiz_id, index, settings.cos_key_prefix
        )
        return uploader(data, key, settings) or None

    max_workers = max(1, min(settings.image_max_concurrency, len(items), 6))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(work, index, question): index for index, question in items}
        for future in as_completed(futures):
            index = futures[future]
            try:
                url = future.result()
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "question_image_failed",
                    user_id=user_id,
                    question_index=index,
                    error=str(exc),
                )
                url = None
            if url:
                results[index] = url
    return results


async def attach_images(
    user_id: int,
    quiz: Quiz,
    settings: Optional[Settings] = None,
    *,
    today: Optional[date] = None,
    usage_repo=image_usage_repository,
    generator: Callable[[str, Settings], Optional[bytes]] = generate_image_bytes,
    uploader: Callable[[bytes, str, Settings], str] = cos_storage_service.upload_image,
) -> Quiz:
    """为题目追加配图；额度预留后并发执行，失败题目退款并保持无图。"""
    settings = settings or get_settings()
    if not quiz.questions or not settings.image_generation_ready:
        return quiz

    usage_date = today or date.today()
    try:
        used = await usage_repo.get_count(user_id, usage_date)
        remaining = max(0, settings.image_daily_limit - int(used))
        count = min(len(quiz.questions), remaining)
        if count <= 0:
            return quiz
        await usage_repo.add_count(user_id, usage_date, count)
    except Exception as exc:  # noqa: BLE001
        logger.warning("image_quota_unavailable", user_id=user_id, error=str(exc))
        return quiz

    items = list(enumerate(quiz.questions))[:count]
    try:
        results = await run_in_threadpool(
            _generate_batch,
            user_id,
            usage_date,
            quiz.quiz_id,
            items,
            settings,
            generator,
            uploader,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("image_batch_failed", user_id=user_id, error=str(exc))
        results = {}

    successes = 0
    for index, url in results.items():
        if url:
            quiz.questions[index].image_url = url
            successes += 1

    failed = count - successes
    if failed > 0:
        try:
            await usage_repo.add_count(user_id, usage_date, -failed)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "image_quota_refund_failed", user_id=user_id, error=str(exc)
            )
    return quiz
