from pydantic import BaseModel, Field

from app.models.quiz import Question
from app.models.report import AnswerRecord


class ScoreSummary(BaseModel):
    total: int = 0
    correct: int = 0
    accuracy: int = 0
    mastered_points: list[str] = Field(default_factory=list)
    weak_points: list[str] = Field(default_factory=list)
    total_duration_ms: int = 0


def is_record_correct(record: AnswerRecord, question: Question | None) -> bool:
    """服务端重算对错：所选集合与标准答案集合完全一致才算对。

    找不到对应题目时，退回信任前端提交的 is_correct。
    """
    if question is None:
        return record.is_correct
    return set(record.selected_answers) == set(question.answer)


def compute_score(questions: list[Question], records: list[AnswerRecord]) -> ScoreSummary:
    """纯逻辑统计：正确率、掌握/薄弱知识点、总用时。不依赖任何外部服务。"""
    qmap = {q.id: q for q in questions}
    correct = 0
    mastered: list[str] = []
    weak: list[str] = []
    total_duration = 0

    for rec in records:
        q = qmap.get(rec.question_id)
        total_duration += rec.duration_ms
        if is_record_correct(rec, q):
            correct += 1
            if q and q.knowledge_point and q.knowledge_point not in mastered:
                mastered.append(q.knowledge_point)
        else:
            if q and q.knowledge_point and q.knowledge_point not in weak:
                weak.append(q.knowledge_point)

    total = len(records)
    accuracy = round(correct / total * 100) if total else 0
    # 同一知识点若既答对又答错，以“薄弱”为准（更保守，利于复盘）
    mastered = [p for p in mastered if p not in weak]

    return ScoreSummary(
        total=total,
        correct=correct,
        accuracy=accuracy,
        mastered_points=mastered,
        weak_points=weak,
        total_duration_ms=total_duration,
    )
