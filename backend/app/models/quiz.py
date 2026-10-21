from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

QuestionType = Literal["single", "multiple", "judge"]
Difficulty = Literal["easy", "medium", "hard"]
DifficultyFilter = Literal["easy", "medium", "hard", "mixed"]


class Option(BaseModel):
    key: str = Field(..., description="选项标识，如 A/B/C/D")
    text: str = Field(..., description="选项内容")


class Source(BaseModel):
    """出题接地的参考来源（取自真实检索/网页抽取/知识库分块，不可由模型编造）。"""

    title: str = Field(..., description="来源标题；知识库来源为文档名")
    url: str = Field("", description="来源链接；知识库来源为空")
    score: Optional[float] = Field(None, description="检索相关度得分（抽取来源可为空）")
    kind: Optional[str] = Field(
        None, description="来源类型：search 检索 / extract 网页抽取 / knowledge_base 知识库"
    )
    doc_id: Optional[str] = Field(None, description="知识库文档业务ID")
    chunk_index: Optional[int] = Field(None, description="知识库分块序号")
    page: Optional[int] = Field(None, description="PDF 出处页码（1 基）")
    snippet: Optional[str] = Field(None, description="知识库分块摘要")


class Question(BaseModel):
    id: str
    type: QuestionType
    stem: str
    options: list[Option]
    answer: list[str] = Field(..., description="正确答案的 key 列表")
    explanation: str
    knowledge_point: str
    difficulty: Difficulty
    image_url: Optional[str] = Field(
        None, description="题目配图的永久访问 URL；未生成配图时为空"
    )


class QuizGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_input: str = Field(..., min_length=1, max_length=4000, description="用户想学习的内容")
    question_count: int = Field(5, ge=3, le=10, description="题目数量，默认 5")
    difficulty: DifficultyFilter = Field("mixed", description="难度筛选")
    use_web_search: bool = Field(False, description="本次是否开启联网检索")
    use_knowledge_base: bool = Field(False, description="本次是否使用个人知识库")
    document_id: Optional[str] = Field(
        None,
        min_length=1,
        max_length=64,
        description="知识库单选文档业务ID；仅 use_knowledge_base=true 时允许",
    )
    generate_images: bool = Field(
        False, description="是否为本次题目生成配图；知识库任务强制关闭"
    )

    @model_validator(mode="after")
    def _validate_source_mode(self) -> "QuizGenerateRequest":
        if self.use_web_search and self.use_knowledge_base:
            raise ValueError("联网检索与知识库不能同时开启")
        if self.use_knowledge_base and not self.document_id:
            raise ValueError("使用知识库时必须选择一份文档")
        if not self.use_knowledge_base and self.document_id:
            raise ValueError("未开启知识库时不能携带文档")
        return self


class Quiz(BaseModel):
    quiz_id: str
    title: str
    summary: str
    interpretation: str = Field("", description="本次出题所选定的领域/角度解读；未接地或主题明确时可为空")
    source_type: str = "text"
    user_input: str
    questions: list[Question]
    sources: list[Source] = Field(default_factory=list, description="参考来源列表（接地时非空）")
    grounded: bool = Field(False, description="本次是否成功联网接地")
