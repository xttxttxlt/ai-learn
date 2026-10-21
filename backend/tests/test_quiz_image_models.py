from app.models.quiz import Option, Question, Quiz, QuizGenerateRequest
from app.models.quiz_job import QuizJobCreateRequest


def _question_payload(**extra):
    payload = {
        "id": "q1",
        "type": "single",
        "stem": "apple 的中文意思是什么？",
        "options": [
            {"key": "A", "text": "苹果"},
            {"key": "B", "text": "香蕉"},
        ],
        "answer": ["A"],
        "explanation": "apple 意为苹果。",
        "knowledge_point": "apple 词义",
        "difficulty": "easy",
    }
    payload.update(extra)
    return payload


def test_question_image_url_defaults_to_none():
    question = Question(**_question_payload())

    assert question.image_url is None


def test_question_accepts_image_url():
    url = "https://bucket-1250000000.cos.ap-guangzhou.myqcloud.com/q1.png"
    question = Question(**_question_payload(image_url=url))

    assert question.image_url == url
    assert question.model_dump()["image_url"] == url


def test_legacy_quiz_payload_without_image_url_still_validates():
    quiz = Quiz(
        quiz_id="quiz_1",
        title="单词闯关",
        summary="",
        user_input="apple",
        questions=[_question_payload()],
    )

    assert quiz.questions[0].image_url is None


def test_generate_images_defaults_to_false():
    req = QuizGenerateRequest(user_input="apple")

    assert req.generate_images is False


def test_job_create_request_accepts_generate_images():
    req = QuizJobCreateRequest(
        user_input="apple", request_id="req_1", generate_images=True
    )

    assert req.generate_images is True


def test_question_with_image_url_keeps_answer_validation_unchanged():
    question = Question(**_question_payload(image_url="https://example.com/q1.png"))
    option_keys = {opt.key for opt in question.options}

    assert set(question.answer).issubset(option_keys)
