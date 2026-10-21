"""个人知识库向量层：百炼 Embedding 工厂 + Chroma 持久化封装。

每个用户一个 collection（kb_user_{user_id}）；分块 ID 为 {doc_id}:{chunk_index}，
写入使用 upsert 保证重试幂等，检索按余弦相关度排序，删除按 doc_id 精确清理。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence

import chromadb
from chromadb.errors import NotFoundError
from langchain_core.tools import BaseTool, StructuredTool
from langchain_openai import OpenAIEmbeddings

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.llm.document_parser import DocumentChunk

logger = get_logger("knowledge_base")

SNIPPET_MAX_CHARS = 300

_clients: dict[str, Any] = {}
_client_lock = threading.Lock()

_embeddings_cache: dict[tuple, Any] = {}
_embeddings_lock = threading.Lock()


class EmbeddingConfigError(Exception):
    """Embedding 未配置或配置非法。"""


class EmbeddingServiceError(Exception):
    """Embedding 调用结果不符合预期（如维度不一致）。"""


@dataclass(frozen=True)
class KnowledgeScope:
    """检索范围：document_ids 非空表示用户选定的单份文档，空表示当前用户全库。"""

    user_id: int
    document_ids: list[str] = field(default_factory=list)

    @property
    def is_document_scope(self) -> bool:
        return bool(self.document_ids)


@dataclass(frozen=True)
class KnowledgeSearchResult:
    doc_id: str
    doc_name: str
    chunk_index: int
    page: Optional[int]
    text: str
    snippet: str
    score: float


def build_embeddings(settings: Optional[Settings] = None) -> OpenAIEmbeddings:
    settings = settings or get_settings()
    if not settings.knowledge_base_ready:
        raise EmbeddingConfigError(
            "知识库未启用或未配置 DASHSCOPE_API_KEY，请完成配置后重试"
        )
    if settings.embedding_batch_size < 1:
        raise EmbeddingConfigError("Embedding 批量大小必须大于 0")
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.dashscope_api_key,
        base_url=settings.embedding_base_url,
        dimensions=settings.embedding_dimensions,
        check_embedding_ctx_length=False,
        chunk_size=settings.embedding_batch_size,
        request_timeout=settings.embedding_timeout,
        max_retries=settings.embedding_max_retries,
    )


def get_embeddings(settings: Optional[Settings] = None) -> Any:
    settings = settings or get_settings()
    key = (
        settings.embedding_base_url,
        settings.embedding_model,
        settings.embedding_dimensions,
        settings.embedding_batch_size,
        settings.embedding_timeout,
        settings.embedding_max_retries,
        settings.dashscope_api_key,
    )
    with _embeddings_lock:
        cached = _embeddings_cache.get(key)
        if cached is None:
            cached = build_embeddings(settings)
            _embeddings_cache[key] = cached
        return cached


def get_chroma_client(settings: Optional[Settings] = None) -> Any:
    settings = settings or get_settings()
    path = str(settings.chroma_persist_path)
    with _client_lock:
        client = _clients.get(path)
        if client is None:
            Path(path).mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=path)
            _clients[path] = client
        return client


def build_vector_store(
    settings: Optional[Settings] = None, embeddings: Optional[Any] = None
) -> "KnowledgeVectorStore":
    settings = settings or get_settings()
    return KnowledgeVectorStore(
        client=get_chroma_client(settings), embeddings=embeddings, settings=settings
    )


class KnowledgeVectorStore:
    def __init__(
        self,
        client: Any,
        settings: Optional[Settings] = None,
        embeddings: Optional[Any] = None,
    ):
        self._client = client
        self._settings = settings or get_settings()
        self._embeddings = embeddings

    @staticmethod
    def collection_name(user_id: int) -> str:
        return f"kb_user_{user_id}"

    def _require_embeddings(self) -> Any:
        if self._embeddings is None:
            self._embeddings = get_embeddings(self._settings)
        return self._embeddings

    def _existing_collection(self, user_id: int) -> Any:
        try:
            return self._client.get_collection(name=self.collection_name(user_id))
        except NotFoundError:
            return None

    def _validate_vectors(self, vectors: Sequence[Sequence[float]]) -> None:
        expected = self._settings.embedding_dimensions
        for vector in vectors:
            if len(vector) != expected:
                raise EmbeddingServiceError(
                    f"Embedding 维度不一致（期望 {expected}，实际 {len(vector)}），"
                    "请检查 EMBEDDING_DIMENSIONS 配置或清空向量库后重建"
                )

    def add_chunks(
        self,
        user_id: int,
        doc_id: str,
        doc_name: str,
        chunks: Sequence[DocumentChunk],
    ) -> int:
        if not chunks:
            return 0
        embeddings = self._require_embeddings()
        batch_size = max(1, self._settings.embedding_batch_size)

        texts = [chunk.text for chunk in chunks]
        vectors: list[list[float]] = []
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            batch_vectors = embeddings.embed_documents(batch)
            self._validate_vectors(batch_vectors)
            vectors.extend(batch_vectors)

        ids: list[str] = []
        metadatas: list[dict[str, Any]] = []
        for index, chunk in enumerate(chunks):
            chunk_index = int(chunk.metadata.get("chunk_index", index))
            ids.append(f"{doc_id}:{chunk_index}")
            metadata: dict[str, Any] = {
                "user_id": user_id,
                "doc_id": doc_id,
                "doc_name": doc_name,
                "chunk_index": chunk_index,
                "status": "ready",
            }
            page = chunk.metadata.get("page")
            if isinstance(page, int):
                metadata["page"] = page
            metadatas.append(metadata)

        collection = self._client.get_or_create_collection(
            name=self.collection_name(user_id),
            configuration={"hnsw": {"space": "cosine"}},
        )
        collection.upsert(
            ids=ids, embeddings=vectors, documents=texts, metadatas=metadatas
        )
        return len(chunks)

    def search(
        self,
        user_id: int,
        query: str,
        top_k: Optional[int] = None,
        document_ids: Optional[Sequence[str]] = None,
    ) -> list[KnowledgeSearchResult]:
        query = (query or "").strip()
        if not query:
            return []
        collection = self._existing_collection(user_id)
        if collection is None:
            return []

        query_vector = self._require_embeddings().embed_query(query)
        self._validate_vectors([query_vector])

        limit = top_k or self._settings.kb_retrieval_top_k
        kwargs: dict[str, Any] = {
            "query_embeddings": [query_vector],
            "n_results": limit,
            "include": ["documents", "metadatas", "distances"],
        }
        if document_ids:
            kwargs["where"] = {"doc_id": {"$in": list(document_ids)}}

        raw = collection.query(**kwargs)
        documents = (raw.get("documents") or [[]])[0]
        metadatas = (raw.get("metadatas") or [[]])[0]
        distances = (raw.get("distances") or [[]])[0]

        results: list[KnowledgeSearchResult] = []
        for text, metadata, distance in zip(documents, metadatas, distances):
            if not text or not metadata:
                continue
            results.append(
                KnowledgeSearchResult(
                    doc_id=str(metadata.get("doc_id", "")),
                    doc_name=str(metadata.get("doc_name", "")),
                    chunk_index=int(metadata.get("chunk_index", 0)),
                    page=metadata.get("page"),
                    text=text,
                    snippet=text[:SNIPPET_MAX_CHARS],
                    score=max(0.0, 1.0 - float(distance)),
                )
            )
        results.sort(key=lambda item: item.score, reverse=True)
        return results

    def delete_document(self, user_id: int, doc_id: str) -> None:
        collection = self._existing_collection(user_id)
        if collection is None:
            return
        collection.delete(where={"doc_id": doc_id})


def _format_knowledge_content(results: Sequence[KnowledgeSearchResult]) -> str:
    lines: list[str] = []
    for index, result in enumerate(results, start=1):
        if result.page is not None:
            location = f"第 {result.page} 页，相关度 {result.score:.2f}"
        else:
            location = f"相关度 {result.score:.2f}"
        lines.append(f"[{index}] 文档：{result.doc_name}（{location}）\n{result.snippet}")
    return "\n\n".join(lines)


def build_knowledge_base_tool(
    scope: KnowledgeScope,
    settings: Optional[Settings] = None,
    store: Optional[KnowledgeVectorStore] = None,
) -> BaseTool:
    settings = settings or get_settings()
    store = store or build_vector_store(settings)

    if scope.is_document_scope:
        description = (
            "检索用户选定的一份文档的相关片段（仅限当前文档，不使用联网）。"
            "仅返回相关度达到阈值的内容；若返回“无足够相关内容”，说明该文档未覆盖此主题。"
        )
    else:
        description = (
            "检索当前用户个人知识库中与问题相关的知识片段。"
            "适合内部资料、上传文档等私有内容；返回文档名、页码、相关度与分块摘要。"
            "仅返回相关度达到阈值的内容；若返回“无足够相关内容”，说明知识库未覆盖该主题，"
            "不应继续引用知识库结果。"
        )

    def _search(query: str) -> tuple[str, dict]:
        try:
            raw_results = store.search(
                scope.user_id,
                query,
                top_k=settings.kb_retrieval_top_k,
                document_ids=list(scope.document_ids) or None,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("knowledge_base_search_failed", error=str(exc))
            return "[知识库检索失败] 请稍后重试", {"results": []}

        if not raw_results:
            return "[知识库无相关结果]", {"results": []}

        results = raw_results
        threshold = max(0.0, min(1.0, settings.kb_min_relevance_score))
        filtered = [result for result in raw_results if result.score >= threshold]
        if not filtered:
            top_score = max(result.score for result in raw_results)
            logger.info(
                "knowledge_base_no_relevant_results",
                user_id=scope.user_id,
                top_score=round(top_score, 3),
                threshold=threshold,
            )
            return (
                f"[知识库无足够相关内容] 最高相关度 {top_score:.2f}，"
                f"低于阈值 {threshold:.2f}；请改用联网检索或按通用知识出题。",
                {"results": []},
            )
        if len(filtered) < len(raw_results):
            logger.info(
                "knowledge_base_results_filtered",
                user_id=scope.user_id,
                raw_count=len(raw_results),
                kept_count=len(filtered),
                threshold=threshold,
            )
        results = filtered

        artifact = {
            "results": [
                {
                    "doc_id": result.doc_id,
                    "doc_name": result.doc_name,
                    "chunk_index": result.chunk_index,
                    "page": result.page,
                    "snippet": result.snippet,
                    "score": result.score,
                }
                for result in results
            ]
        }
        return _format_knowledge_content(results), artifact

    return StructuredTool.from_function(
        func=_search,
        name="search_knowledge_base",
        description=description,
        response_format="content_and_artifact",
    )
