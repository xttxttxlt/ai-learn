import uuid


def generate_quiz_id() -> str:
    return "quiz_" + uuid.uuid4().hex[:16]


def generate_job_id() -> str:
    return "job_" + uuid.uuid4().hex[:16]


def generate_doc_id() -> str:
    return "doc_" + uuid.uuid4().hex[:16]
