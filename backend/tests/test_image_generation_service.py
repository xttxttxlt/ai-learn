import json
import threading
import time
from datetime import date

import httpx

from app.core.config import Settings
from app.models.quiz import Option, Question, Quiz
from app.services import cos_storage_service, image_generation_service

DAY = date(2026, 10, 21)


def _settings(**overrides):
    values = {
        "_env_file": None,
        "dashscope_api_key": "ds-key",
        "cos_secret_id": "secret-id",
        "cos_secret_key": "secret-key",
        "cos_region": "ap-guangzhou",
        "cos_bucket": "bucket-1250000000",
        "image_base_url": "https://dashscope.aliyuncs.com/api/v1",
        "image_model": "qwen-image-3.0",
        "image_size": "512*512",
        "image_timeout_seconds": 5,
        "image_max_concurrency": 6,
        "image_daily_limit": 100,
    }
    values.update(overrides)
    return Settings(**values)


def _question(index: int, **overrides):
    values = {
        "id": f"q{index + 1}",
        "type": "single",
        "stem": f"第 {index + 1} 题的题干",
        "options": [
            Option(key="A", text=f"正确答案 {index + 1}"),
            Option(key="B", text="干扰项"),
        ],
        "answer": ["A"],
        "explanation": "解析",
        "knowledge_point": f"知识点 {index + 1}",
        "difficulty": "easy",
    }
    values.update(overrides)
    return Question(**values)


def _quiz(count=5, **question_overrides):
    return Quiz(
        quiz_id="quiz_test",
        title="测试题库",
        summary="",
        user_input="测试",
        questions=[_question(i, **question_overrides) for i in range(count)],
    )


def _http_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), timeout=5)


def test_build_image_prompt_contains_subject_and_no_text_rule():
    prompt = image_generation_service.build_image_prompt(
        _question(
            0,
            stem="以下哪个单词表示苹果？",
            knowledge_point="apple 词义",
            options=[Option(key="A", text="苹果"), Option(key="B", text="香蕉")],
            answer=["A"],
        )
    )

    assert "苹果" in prompt
    assert "以下哪个单词表示苹果？" not in prompt
    assert "香蕉" not in prompt
    assert "不要出现任何文字、字母、数字" in prompt or "不要文字、不要字母、不要数字" in prompt
    assert "不要拼贴" in prompt
    assert "卡片" in prompt


def test_build_image_prompt_uses_chinese_quoted_subject_for_english_answer():
    prompt = image_generation_service.build_image_prompt(
        _question(
            0,
            stem="“微波炉”对应的英文是？",
            knowledge_point="厨房电器词汇",
            options=[
                Option(key="A", text="oven"),
                Option(key="B", text="microwave oven"),
            ],
            answer=["B"],
        )
    )

    assert "微波炉" in prompt
    assert "microwave oven" not in prompt
    assert "“微波炉”对应的英文是？" not in prompt


def test_build_image_prompt_truncates_long_fields():
    prompt = image_generation_service.build_image_prompt(
        _question(
            0,
            options=[Option(key="A", text="长" * 1000)],
            knowledge_point="知识" * 200,
        )
    )

    assert len(prompt) < 700
    assert "长" * 61 not in prompt


def test_build_image_prompt_handles_missing_answer_text():
    prompt = image_generation_service.build_image_prompt(
        _question(0, answer=[], options=[Option(key="A", text="苹果")])
    )

    assert "知识点 1" in prompt
    assert "不要文字" in prompt


def test_generate_image_bytes_posts_expected_payload_and_downloads_image():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST":
            payload = json.loads(request.content)
            assert payload["model"] == "qwen-image-3.0"
            assert payload["input"]["messages"][0]["content"][0]["text"] == "画一只苹果"
            assert payload["parameters"]["size"] == "512*512"
            assert payload["parameters"]["n"] == 1
            assert request.headers["Authorization"] == "Bearer ds-key"
            return httpx.Response(
                200,
                json={
                    "output": {
                        "choices": [
                            {
                                "message": {
                                    "content": [
                                        {"image": "https://example.com/tmp.png"}
                                    ]
                                }
                            }
                        ]
                    }
                },
            )
        return httpx.Response(200, content=b"PNG-BYTES")

    client = _http_client(handler)
    try:
        data = image_generation_service.generate_image_bytes(
            "画一只苹果", _settings(), client=client
        )
    finally:
        client.close()

    assert data == b"PNG-BYTES"
    assert [r.method for r in requests] == ["POST", "GET"]
    assert requests[0].url.path.endswith(
        "/services/aigc/multimodal-generation/generation"
    )


def test_generate_image_bytes_returns_none_on_http_error():
    client = _http_client(lambda request: httpx.Response(500, text="boom"))
    try:
        assert (
            image_generation_service.generate_image_bytes(
                "x", _settings(image_max_retries=0), client=client
            )
            is None
        )
    finally:
        client.close()


def test_generate_image_bytes_returns_none_when_response_has_no_image():
    client = _http_client(
        lambda request: httpx.Response(
            200,
            json={"output": {"choices": [{"message": {"content": [{"text": "x"}]}}]}},
        )
    )
    try:
        assert (
            image_generation_service.generate_image_bytes("x", _settings(), client=client)
            is None
        )
    finally:
        client.close()


def test_generate_image_bytes_returns_none_on_network_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network down", request=request)

    client = _http_client(handler)
    try:
        assert (
            image_generation_service.generate_image_bytes(
                "x", _settings(image_max_retries=0), client=client
            )
            is None
        )
    finally:
        client.close()


def test_generate_image_bytes_retries_429_then_succeeds():
    attempts = {"post": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            attempts["post"] += 1
            if attempts["post"] < 3:
                return httpx.Response(429, text="rate limited")
            return httpx.Response(
                200,
                json={
                    "output": {
                        "choices": [
                            {
                                "message": {
                                    "content": [
                                        {"image": "https://example.com/tmp.png"}
                                    ]
                                }
                            }
                        ]
                    }
                },
            )
        return httpx.Response(200, content=b"PNG")

    client = _http_client(handler)
    try:
        data = image_generation_service.generate_image_bytes(
            "x",
            _settings(image_max_retries=2, image_retry_backoff_seconds=0),
            client=client,
        )
    finally:
        client.close()

    assert data == b"PNG"
    assert attempts["post"] == 3


def test_generate_image_bytes_returns_none_after_retry_exhausted():
    attempts = {"post": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["post"] += 1
        return httpx.Response(429, text="rate limited")

    client = _http_client(handler)
    try:
        assert (
            image_generation_service.generate_image_bytes(
                "x",
                _settings(image_max_retries=1, image_retry_backoff_seconds=0),
                client=client,
            )
            is None
        )
    finally:
        client.close()

    assert attempts["post"] == 2


def test_build_object_key_contains_user_date_quiz_and_question():
    key = cos_storage_service.build_object_key(7, DAY, "quiz_1", 0)

    assert key == "question-images/7/20261021/quiz_1/q1.png"


def test_build_public_url_uses_default_cos_domain():
    url = cos_storage_service.build_public_url("question-images/a.png", _settings())

    assert url == (
        "https://bucket-1250000000.cos.ap-guangzhou.myqcloud.com/question-images/a.png"
    )


def test_build_public_url_uses_custom_base_without_double_slash():
    url = cos_storage_service.build_public_url(
        "question-images/a.png",
        _settings(cos_public_base_url="https://cdn.example.com/"),
    )

    assert url == "https://cdn.example.com/question-images/a.png"


def test_upload_image_puts_object_and_returns_url(monkeypatch):
    calls: list[dict] = []

    class FakeClient:
        def put_object(self, **kwargs):
            calls.append(kwargs)
            return {"ETag": "etag"}

    monkeypatch.setattr(
        cos_storage_service, "_create_client", lambda settings: FakeClient()
    )

    url = cos_storage_service.upload_image(
        b"image-bytes", "question-images/a.png", _settings()
    )

    assert url.endswith("/question-images/a.png")
    assert calls[0]["Bucket"] == "bucket-1250000000"
    assert calls[0]["Body"] == b"image-bytes"
    assert calls[0]["Key"] == "question-images/a.png"
    assert calls[0]["ContentType"] == "image/png"
    assert calls[0]["ACL"] == "public-read"


def test_upload_image_returns_empty_on_error(monkeypatch):
    class FakeClient:
        def put_object(self, **kwargs):
            raise RuntimeError("cos down")

    monkeypatch.setattr(
        cos_storage_service, "_create_client", lambda settings: FakeClient()
    )

    assert cos_storage_service.upload_image(b"x", "key", _settings()) == ""


class FakeUsageRepo:
    def __init__(self, count=0, fail_read=False, fail_reserve=False):
        self.count = count
        self.fail_read = fail_read
        self.fail_reserve = fail_reserve
        self.calls: list[tuple] = []

    async def get_count(self, user_id, usage_date):
        self.calls.append(("get", user_id, usage_date))
        if self.fail_read:
            raise RuntimeError("db down")
        return self.count

    async def add_count(self, user_id, usage_date, delta):
        self.calls.append(("add", user_id, usage_date, delta))
        if self.fail_reserve and delta > 0:
            raise RuntimeError("db down")


class FakeGenerator:
    def __init__(self, fail_indices=(), delay=0.0):
        self.fail_indices = set(fail_indices)
        self.delay = delay
        self.calls: list[str] = []
        self._lock = threading.Lock()
        self._active = 0
        self.max_active = 0

    def __call__(self, prompt, settings):
        with self._lock:
            self._active += 1
            self.max_active = max(self.max_active, self._active)
        try:
            self.calls.append(prompt)
            if self.delay:
                time.sleep(self.delay)
            if len(self.calls) - 1 in self.fail_indices:
                raise RuntimeError("generate failed")
            return b"image"
        finally:
            with self._lock:
                self._active -= 1


class FakeUploader:
    def __init__(self, fail=False):
        self.fail = fail
        self.keys: list[str] = []

    def __call__(self, data, key, settings):
        self.keys.append(key)
        return "" if self.fail else f"https://cdn.example.com/{key}"


async def test_attach_images_generates_all_questions():
    quiz = _quiz(5)
    repo = FakeUsageRepo()
    generator = FakeGenerator()
    uploader = FakeUploader()

    result = await image_generation_service.attach_images(
        7,
        quiz,
        _settings(),
        today=DAY,
        usage_repo=repo,
        generator=generator,
        uploader=uploader,
    )

    assert all(q.image_url and q.image_url.startswith("https://cdn.example.com/") for q in result.questions)
    assert len(generator.calls) == 5
    assert ("add", 7, DAY, 5) in repo.calls
    assert not any(call[3] < 0 for call in repo.calls if call[0] == "add")


async def test_attach_images_refunds_failed_generation():
    quiz = _quiz(5)
    repo = FakeUsageRepo()
    generator = FakeGenerator(fail_indices={1, 3})
    uploader = FakeUploader()

    result = await image_generation_service.attach_images(
        7, quiz, _settings(), today=DAY, usage_repo=repo, generator=generator, uploader=uploader
    )

    assert sum(1 for q in result.questions if q.image_url) == 3
    assert result.questions[1].image_url is None
    assert result.questions[3].image_url is None
    assert ("add", 7, DAY, 5) in repo.calls
    assert ("add", 7, DAY, -2) in repo.calls


async def test_attach_images_only_uses_remaining_quota():
    quiz = _quiz(5)
    repo = FakeUsageRepo(count=98)
    generator = FakeGenerator()
    uploader = FakeUploader()

    result = await image_generation_service.attach_images(
        7, quiz, _settings(), today=DAY, usage_repo=repo, generator=generator, uploader=uploader
    )

    assert sum(1 for q in result.questions if q.image_url) == 2
    assert len(generator.calls) == 2
    assert ("add", 7, DAY, 2) in repo.calls


async def test_attach_images_skips_when_quota_exhausted():
    quiz = _quiz(5)
    repo = FakeUsageRepo(count=100)
    generator = FakeGenerator()
    uploader = FakeUploader()

    result = await image_generation_service.attach_images(
        7, quiz, _settings(), today=DAY, usage_repo=repo, generator=generator, uploader=uploader
    )

    assert all(q.image_url is None for q in result.questions)
    assert generator.calls == []
    assert not any(call[0] == "add" for call in repo.calls)


async def test_attach_images_skips_when_not_configured():
    quiz = _quiz(2)
    repo = FakeUsageRepo()
    generator = FakeGenerator()
    uploader = FakeUploader()

    await image_generation_service.attach_images(
        7,
        quiz,
        _settings(cos_bucket=""),
        today=DAY,
        usage_repo=repo,
        generator=generator,
        uploader=uploader,
    )

    assert generator.calls == []
    assert repo.calls == []


async def test_attach_images_swallows_quota_read_error():
    quiz = _quiz(2)
    repo = FakeUsageRepo(fail_read=True)
    generator = FakeGenerator()
    uploader = FakeUploader()

    result = await image_generation_service.attach_images(
        7, quiz, _settings(), today=DAY, usage_repo=repo, generator=generator, uploader=uploader
    )

    assert all(q.image_url is None for q in result.questions)
    assert generator.calls == []


async def test_attach_images_swallows_quota_reserve_error():
    quiz = _quiz(2)
    repo = FakeUsageRepo(fail_reserve=True)
    generator = FakeGenerator()
    uploader = FakeUploader()

    result = await image_generation_service.attach_images(
        7, quiz, _settings(), today=DAY, usage_repo=repo, generator=generator, uploader=uploader
    )

    assert all(q.image_url is None for q in result.questions)
    assert generator.calls == []


async def test_attach_images_refunds_upload_failures():
    quiz = _quiz(3)
    repo = FakeUsageRepo()
    generator = FakeGenerator()
    uploader = FakeUploader(fail=True)

    result = await image_generation_service.attach_images(
        7, quiz, _settings(), today=DAY, usage_repo=repo, generator=generator, uploader=uploader
    )

    assert all(q.image_url is None for q in result.questions)
    assert ("add", 7, DAY, 3) in repo.calls
    assert ("add", 7, DAY, -3) in repo.calls


async def test_attach_images_runs_concurrently():
    quiz = _quiz(5)
    repo = FakeUsageRepo()
    generator = FakeGenerator(delay=0.05)
    uploader = FakeUploader()

    await image_generation_service.attach_images(
        7, quiz, _settings(), today=DAY, usage_repo=repo, generator=generator, uploader=uploader
    )

    assert generator.max_active >= 2
