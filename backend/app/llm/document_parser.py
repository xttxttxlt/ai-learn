"""文档解析与分块：PDF / Word(.docx) / Markdown / 纯文本。

解析使用 LangChain 文档加载器，切分使用 RecursiveCharacterTextSplitter；
输出分块携带用户、文档与页码元数据，供向量库检索与来源展示。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_community.document_loaders import (
    Docx2txtLoader,
    PyPDFLoader,
    TextLoader,
)
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger("document_parser")

SUPPORTED_EXTENSIONS = {"pdf", "docx", "md", "txt"}

_SPLIT_SEPARATORS = ["\n\n", "\n", "。", "？", "！", "；", "，", " ", ""]

_LINK_RE = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_BOLD_RE = re.compile(r"(?<!\w)(\*\*|__)(?=\S)(.*?\S)\1(?!\w)")
_ITALIC_RE = re.compile(r"(?<!\w)(\*|_)(?=\S)(.*?\S)\1(?!\w)")
_CODE_RE = re.compile(r"`([^`]*)`")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s*")
_QUOTE_RE = re.compile(r"^\s*>\s?")
_LIST_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_RULE_RE = re.compile(r"^\s*(?:[-*_]\s*){3,}$")


class DocumentParseError(Exception):
    """解析/分块失败：message 面向用户，内部堆栈只进日志。"""


@dataclass(frozen=True)
class DocumentChunk:
    text: str
    metadata: dict[str, Any]


def normalize_extension(file_ext: str) -> str:
    return (file_ext or "").lower().lstrip(".")


def _load_with(loader_factory: Any, path: Path, ext: str) -> list[Document]:
    try:
        return loader_factory(str(path)).load()
    except DocumentParseError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("document_load_failed", ext=ext, error=str(exc))
        raise DocumentParseError("文档解析失败，请确认文件未损坏或格式正确") from exc


def _markdown_to_text(raw: str) -> str:
    """轻量清洗 Markdown 标记；避免 unstructured 依赖 NLTK 资源导致的离线阻塞。"""
    lines: list[str] = []
    in_fence = False
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            lines.append(line.rstrip())
            continue
        text = _HEADING_RE.sub("", line)
        text = _QUOTE_RE.sub("", text)
        text = _LIST_RE.sub("", text)
        text = _LINK_RE.sub(r"\1", text)
        text = _BOLD_RE.sub(r"\2", text)
        text = _ITALIC_RE.sub(r"\2", text)
        text = _CODE_RE.sub(r"\1", text)
        if _RULE_RE.match(text):
            text = ""
        lines.append(text.rstrip())
    return "\n".join(lines)


def _load_documents(path: Path, ext: str) -> list[Document]:
    if ext == "pdf":
        return _load_with(PyPDFLoader, path, ext)
    if ext == "docx":
        return _load_with(Docx2txtLoader, path, ext)
    if ext == "txt":
        return _load_with(
            lambda p: TextLoader(p, encoding="utf-8"), path, ext
        )
    if ext == "md":
        documents = _load_with(
            lambda p: TextLoader(p, encoding="utf-8"), path, ext
        )
        return [
            Document(
                page_content=_markdown_to_text(document.page_content),
                metadata=document.metadata,
            )
            for document in documents
        ]
    raise DocumentParseError("不支持的文件格式，仅支持 PDF、Word（.docx）、Markdown 与纯文本")


def _page_number(metadata: dict[str, Any]) -> int | None:
    value = metadata.get("page")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value) + 1


def parse_document(
    file_path: str | Path,
    file_ext: str,
    *,
    user_id: int,
    doc_id: str,
    doc_name: str,
    settings: Settings | None = None,
) -> list[DocumentChunk]:
    """解析文档并切分为带元数据的分块；无可用文本或超过上限时抛 DocumentParseError。"""
    ext = normalize_extension(file_ext)
    if ext not in SUPPORTED_EXTENSIONS:
        raise DocumentParseError(
            "不支持的文件格式，仅支持 PDF、Word（.docx）、Markdown 与纯文本"
        )

    path = Path(file_path)
    documents = _load_documents(path, ext)
    settings = settings or get_settings()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.kb_chunk_size,
        chunk_overlap=settings.kb_chunk_overlap,
        add_start_index=True,
        separators=_SPLIT_SEPARATORS,
    )

    chunks: list[DocumentChunk] = []
    for document in documents:
        for piece in splitter.split_documents([document]):
            text = piece.page_content.strip()
            if not text:
                continue
            metadata: dict[str, Any] = {
                "user_id": user_id,
                "doc_id": doc_id,
                "doc_name": doc_name,
                "chunk_index": len(chunks),
            }
            page = _page_number(piece.metadata)
            if page is not None:
                metadata["page"] = page
            chunks.append(DocumentChunk(text=text, metadata=metadata))

    if not chunks:
        raise DocumentParseError("未提取到可用文本，请确认文档内容不是空白或扫描件")

    if len(chunks) > settings.kb_max_chunks_per_doc:
        raise DocumentParseError(
            f"文档内容过多（超过 {settings.kb_max_chunks_per_doc} 个知识片段），请拆分后上传"
        )

    return chunks
