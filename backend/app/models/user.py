from typing import Any, Optional

from pydantic import BaseModel, Field

from app.models.quiz import Question


class LoginRequest(BaseModel):
    code: str = Field(..., min_length=1, description="wx.login() 返回的临时登录凭证")


class UserOut(BaseModel):
    id: int
    nickname: str
    avatar_url: str
    total_coins: int


class LoginResponse(BaseModel):
    token: str
    user: UserOut


class ProfileOut(UserOut):
    quiz_count: int = 0
    correct_count: int = 0
    average_accuracy: int = 0


class ProfileUpdateRequest(BaseModel):
    nickname: Optional[str] = Field(None, min_length=1, max_length=100)
    avatar_url: Optional[str] = Field(None, max_length=500)


class QuizHistoryItem(BaseModel):
    quiz_id: str
    title: str
    accuracy: Optional[int] = Field(None, description="正确率 0-100；未完成答题时为 None")
    question_count: Optional[int] = None
    created_at: str


class QuizHistoryList(BaseModel):
    items: list[QuizHistoryItem]
    total: int
    page: int
    page_size: int


class QuizDetail(BaseModel):
    quiz_id: str
    title: str
    summary: str
    created_at: str
    questions: list[Question] = Field(default_factory=list)
    answer_records: list[dict[str, Any]] = Field(default_factory=list)
    report: Optional[dict[str, Any]] = None
    accuracy: Optional[int] = None
