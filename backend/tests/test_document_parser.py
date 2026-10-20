import pytest
from langchain_core.documents import Document

from app.core.config import Settings
from app.llm import document_parser
from app.llm.document_parser import DocumentParseError, parse_document


def _settings(**kwargs):
    return Settings(_env_file=None, **kwargs)


def _parse(path, ext, settings=None):
    return parse_document(
        path,
        ext,
        user_id=7,
        doc_id="doc_1",
        doc_name="资料.md",
        settings=settings or _settings(),
    )


class FakeLoader:
    def __init__(self, docs=None, error=None):
        self.docs = docs or []
        self.error = error

    def load(self):
        if self.error:
            raise self.error
        return self.docs


def test_pdf_keeps_1_based_page_numbers(tmp_path, monkeypatch):
    path = tmp_path / "a.pdf"
    path.write_bytes(b"%PDF-fake")
    docs = [
        Document(page_content="第一页内容", metadata={"page": 0}),
        Document(page_content="第二页内容", metadata={"page": 1}),
    ]
    monkeypatch.setattr(document_parser, "PyPDFLoader", lambda _: FakeLoader(docs))

    chunks = parse_document(
        path, "pdf", user_id=7, doc_id="doc_1", doc_name="资料.pdf", settings=_settings()
    )

    assert [c.metadata["page"] for c in chunks] == [1, 2]
    assert [c.text for c in chunks] == ["第一页内容", "第二页内容"]


def test_docx_extracts_text(tmp_path, monkeypatch):
    path = tmp_path / "a.docx"
    path.write_bytes(b"fake")
    monkeypatch.setattr(
        document_parser,
        "Docx2txtLoader",
        lambda _: FakeLoader([Document(page_content="Word 正文")]),
    )

    chunks = parse_document(
        path, ".docx", user_id=7, doc_id="doc_1", doc_name="资料.docx", settings=_settings()
    )

    assert [c.text for c in chunks] == ["Word 正文"]
    assert "page" not in chunks[0].metadata


def test_markdown_extracts_text_and_strips_syntax(tmp_path):
    path = tmp_path / "a.md"
    path.write_text(
        "# 标题\n\n正文 **重点** 与 [链接](https://example.com)\n\n```\ncode\n```\n\n> 引用",
        encoding="utf-8",
    )

    chunks = _parse(path, "md")

    text = chunks[0].text
    assert "标题" in text
    assert "正文 重点 与 链接" in text
    assert "#" not in text
    assert "**" not in text
    assert "https://example.com" not in text
    assert "code" in text
    assert "引用" in text


def test_markdown_does_not_depend_on_nltk(tmp_path):
    path = tmp_path / "a.md"
    path.write_text("Markdown 纯文本", encoding="utf-8")

    chunks = _parse(path, "md")

    assert chunks[0].text == "Markdown 纯文本"


def test_txt_parses_real_file(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("纯文本内容", encoding="utf-8")

    chunks = _parse(path, "txt")

    assert chunks[0].text == "纯文本内容"


def test_empty_document_raises_readable_error(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("   \n  ", encoding="utf-8")

    with pytest.raises(DocumentParseError) as excinfo:
        _parse(path, "txt")

    assert "未提取到可用文本" in str(excinfo.value)


def test_loader_failure_is_wrapped_without_internal_detail(tmp_path, monkeypatch):
    path = tmp_path / "a.docx"
    path.write_bytes(b"fake")
    monkeypatch.setattr(
        document_parser,
        "Docx2txtLoader",
        lambda _: FakeLoader(error=RuntimeError("secret-internal-stack")),
    )

    with pytest.raises(DocumentParseError) as excinfo:
        _parse(path, "docx")

    message = str(excinfo.value)
    assert "文档解析失败" in message
    assert "secret-internal-stack" not in message


def test_unsupported_extension_raises(tmp_path):
    path = tmp_path / "a.doc"
    path.write_bytes(b"fake")

    with pytest.raises(DocumentParseError) as excinfo:
        _parse(path, "doc")

    assert "不支持" in str(excinfo.value)


def test_chunk_metadata_and_sequential_index(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("第一段内容。\n\n" + "很长的正文。" * 100, encoding="utf-8")
    settings = _settings(kb_chunk_size=50, kb_chunk_overlap=10)

    chunks = _parse(path, "txt", settings=settings)

    assert len(chunks) > 1
    for index, chunk in enumerate(chunks):
        assert chunk.metadata["user_id"] == 7
        assert chunk.metadata["doc_id"] == "doc_1"
        assert chunk.metadata["doc_name"] == "资料.md"
        assert chunk.metadata["chunk_index"] == index
        assert chunk.text.strip() == chunk.text


def test_chunk_size_and_overlap(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("abcdefghij" * 50, encoding="utf-8")
    settings = _settings(kb_chunk_size=100, kb_chunk_overlap=20)

    chunks = _parse(path, "txt", settings=settings)

    assert len(chunks) > 1
    assert all(len(c.text) <= 100 for c in chunks)
    assert chunks[1].text.startswith(chunks[0].text[-20:])


def test_too_many_chunks_raises(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("abcdefghij" * 50, encoding="utf-8")
    settings = _settings(kb_chunk_size=100, kb_chunk_overlap=0, kb_max_chunks_per_doc=2)

    with pytest.raises(DocumentParseError) as excinfo:
        _parse(path, "txt", settings=settings)

    assert "文档内容过多" in str(excinfo.value)
