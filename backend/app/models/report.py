from pydantic import BaseModel, Field

from app.models.quiz import Question


class AnswerRecord(BaseModel):
    question_id: str
    selected_answers: list[str] = Field(default_factory=list)
    is_correct: bool = False
    duration_ms: int = Field(0, ge=0)


class ReportGenerateRequest(BaseModel):
    quiz_id: str = ""
    topic: str = ""
    questions: list[Question] = Field(default_factory=list)
    answer_records: list[AnswerRecord] = Field(default_factory=list)


class Report(BaseModel):
    accuracy: int = Field(..., ge=0, le=100)
    mastered_points: list[str] = Field(default_factory=list)
    weak_points: list[str] = Field(default_factory=list)
    three_line_summary: list[str] = Field(default_factory=list)
    advice: list[str] = Field(default_factory=list)
    share_quote: str = ""
