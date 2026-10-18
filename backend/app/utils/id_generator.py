import uuid


def generate_quiz_id() -> str:
    return "quiz_" + uuid.uuid4().hex[:16]
