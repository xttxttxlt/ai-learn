"""LangChain with_structured_output 使用的 Pydantic 输出 Schema。

注意：json_mode 不会自动把 schema 注入 prompt，因此 prompt 中必须显式描述结构
（见 app/prompts/ 下的 SCHEMA_EXAMPLE 常量）。
"""

from typing import Literal

from pydantic import BaseModel, Field


# ===== 出题链 =====
class OptionSchema(BaseModel):
    key: str = Field(description="选项标识，如 A、B、C、D")
    text: str = Field(description="选项文本内容")


class QuestionSchema(BaseModel):
    id: str = Field(description="题目编号，如 q1、q2")
    type: Literal["single", "multiple", "judge"] = Field(
        description="题型：single 单选、multiple 多选、judge 判断"
    )
    stem: str = Field(description="题干")
    options: list[OptionSchema] = Field(description="选项列表，至少 2 项")
    answer: list[str] = Field(
        description="正确答案的 key 数组；单选与判断只含 1 个，多选含 2 个或以上"
    )
    explanation: str = Field(description="详细讲解，通俗简洁，适合初学者与移动端阅读")
    knowledge_point: str = Field(description="知识点标签")
    difficulty: Literal["easy", "medium", "hard"] = Field(description="难度")


class QuizOutputSchema(BaseModel):
    title: str = Field(description="学习主题标题")
    summary: str = Field(description="本次题库的主题摘要")
    questions: list[QuestionSchema] = Field(description="题目列表")


# ===== 报告链 =====
class ReportOutputSchema(BaseModel):
    accuracy: int = Field(description="本次正确率（0-100 的整数）")
    mastered_points: list[str] = Field(description="掌握较好的知识点")
    weak_points: list[str] = Field(description="薄弱、需要加强的知识点")
    three_line_summary: list[str] = Field(description="三句知识总结，恰好 3 句")
    advice: list[str] = Field(description="后续复习建议，2-3 条，可执行")
    share_quote: str = Field(description="一句可用于分享的学习金句")
