from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.models.quiz import Quiz, QuizGenerateRequest

QuizJobStatus = Literal["pending", "running", "completed", "failed"]


class QuizJobCreateRequest(QuizGenerateRequest):
    request_id: str = Field(..., min_length=1, max_length=64, description="客户端幂等请求ID")


class QuizJobCreated(BaseModel):
    job_id: str
    status: QuizJobStatus


class QuizJobOut(BaseModel):
    job_id: str
    status: QuizJobStatus
    quiz: Optional[Quiz] = Field(None, description="completed 时的题库")
    error: Optional[str] = Field(None, description="failed 时的可读错误说明")
