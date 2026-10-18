from typing import Literal

from pydantic import BaseModel, Field

QuestionType = Literal["single", "multiple", "judge"]
Difficulty = Literal["easy", "medium", "hard"]
DifficultyFilter = Literal["easy", "medium", "hard", "mixed"]


class Option(BaseModel):
    key: str = Field(..., description="选项标识，如 A/B/C/D")
    text: str = Field(..., description="选项内容")


class Question(BaseModel):
    id: str
    type: QuestionType
    stem: str
    options: list[Option]
    answer: list[str] = Field(..., description="正确答案的 key 列表")
    explanation: str
    knowledge_point: str
    difficulty: Difficulty


class QuizGenerateRequest(BaseModel):
    user_input: str = Field(..., min_length=1, max_length=4000, description="用户想学习的内容")
    question_count: int = Field(5, ge=3, le=10, description="题目数量，默认 5")
    difficulty: DifficultyFilter = Field("mixed", description="难度筛选")


class Quiz(BaseModel):
    quiz_id: str
    title: str
    summary: str
    source_type: str = "text"
    user_input: str
    questions: list[Question]
