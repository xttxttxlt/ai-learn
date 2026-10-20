from typing import Literal, Optional

from pydantic import BaseModel, Field

KnowledgeDocumentStatus = Literal["pending", "processing", "ready", "failed"]


class KnowledgeDocumentOut(BaseModel):
    doc_id: str
    file_name: str
    file_ext: str
    file_size: int = 0
    status: KnowledgeDocumentStatus
    chunk_count: int = 0
    error_message: Optional[str] = None
    created_at: str = ""
    finished_at: Optional[str] = None


class KnowledgeBaseStats(BaseModel):
    total_documents: int = 0
    ready_documents: int = 0
    processing_documents: int = 0
    failed_documents: int = 0
    total_chunks: int = 0


class KnowledgeBaseOverview(BaseModel):
    stats: KnowledgeBaseStats = Field(default_factory=KnowledgeBaseStats)
    documents: list[KnowledgeDocumentOut] = Field(default_factory=list)
