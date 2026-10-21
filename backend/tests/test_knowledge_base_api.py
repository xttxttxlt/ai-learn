from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.core.auth import create_token
from app.core.config import Settings
from app.main import app
from app.services import knowledge_base_service
from tests.fake_db import FakeDB

client = TestClient(app)

HEADERS = {"Authorization": f"Bearer {create_token(7, 'openid_test')}"}
OTHER_HEADERS = {"Authorization": f"Bearer {create_token(8, 'openid_other')}"}


def _settings(tmp_path, **kwargs):
    values = {
        "dashscope_api_key": "test-key",
        "kb_upload_dir": str(tmp_path / "upload"),
        "chroma_persist_dir": str(tmp_path / "chroma"),
        "kb_max_file_mb": 1,
    }
    values.update(kwargs)
    return Settings(_env_file=None, **values)


def _doc_row(**kwargs):
    row = {
        "doc_id": "doc_1",
        "user_id": 7,
        "file_name": "笔记.md",
        "file_ext": "md",
        "file_size": 4,
        "file_path": "7/doc_1/笔记.md",
        "status": "processing",
        "chunk_count": 0,
        "error_message": None,
        "created_at": datetime(2026, 10, 20, 10, 0, 0),
        "finished_at": None,
    }
    row.update(kwargs)
    return row


class FakeStore:
    def __init__(self):
        self.deleted: list[tuple] = []

    def delete_document(self, user_id, doc_id):
        self.deleted.append((user_id, doc_id))


@pytest.fixture
def upload_env(monkeypatch, tmp_path):
    settings = _settings(tmp_path)
    monkeypatch.setattr(knowledge_base_service, "get_settings", lambda: settings)
    created: list[dict] = []
    scheduled: list[tuple] = []

    async def fake_create(**kwargs):
        created.append(kwargs)
        return 1

    def fake_schedule(*args, **kwargs):
        scheduled.append((args, kwargs))

    monkeypatch.setattr(
        knowledge_base_service.knowledge_document_repository,
        "create_document",
        fake_create,
    )
    monkeypatch.setattr(knowledge_base_service, "schedule_ingestion", fake_schedule)
    monkeypatch.setattr(
        knowledge_base_service, "generate_doc_id", lambda: "doc_fixed"
    )
    return settings, created, scheduled


def test_get_overview_requires_login():
    resp = client.get("/api/v1/knowledge-base")

    assert resp.status_code == 200
    assert resp.json()["code"] == 4010


def test_get_overview_returns_stats_and_documents(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.fetch_one_queue = [
        {
            "total_documents": 1,
            "ready_documents": 0,
            "processing_documents": 1,
            "failed_documents": 0,
            "total_chunks": 0,
        }
    ]
    fake.fetch_all_queue = [[_doc_row()]]

    resp = client.get("/api/v1/knowledge-base", headers=HEADERS)

    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["stats"]["processing_documents"] == 1
    assert body["data"]["documents"][0]["doc_id"] == "doc_1"
    assert body["data"]["documents"][0]["status"] == "processing"


def test_list_documents_requires_login():
    resp = client.get("/api/v1/knowledge-base/documents")

    assert resp.status_code == 200
    assert resp.json()["code"] == 4010


def test_list_documents_paginated(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    fake.fetch_one_queue = [{"total": 12}]
    fake.fetch_all_queue = [[_doc_row(doc_id="doc_11")]]

    resp = client.get(
        "/api/v1/knowledge-base/documents?page=2&page_size=10", headers=HEADERS
    )

    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["total"] == 12
    assert data["page"] == 2
    assert data["page_size"] == 10
    assert data["items"][0]["doc_id"] == "doc_11"
    assert fake.fetch_all_calls[0][1] == (7, 10, 10)


def test_upload_requires_login():
    resp = client.post(
        "/api/v1/knowledge-base/documents",
        files={"file": ("a.md", b"content", "text/markdown")},
    )

    assert resp.status_code == 200
    assert resp.json()["code"] == 4010


def test_upload_markdown_succeeds(upload_env, monkeypatch):
    settings, created, scheduled = upload_env
    monkeypatch.setattr(
        knowledge_base_service, "beijing_now", lambda: datetime(2026, 10, 21, 15, 30)
    )

    resp = client.post(
        "/api/v1/knowledge-base/documents",
        files={"file": ("笔记.md", b"# hello", "text/markdown")},
        headers=HEADERS,
    )

    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["doc_id"] == "doc_fixed"
    assert body["data"]["file_name"] == "笔记.md"
    assert body["data"]["status"] == "pending"
    assert body["data"]["created_at"] == "2026-10-21 15:30:00"
    saved = settings.kb_upload_path / "7" / "doc_fixed" / "笔记.md"
    assert saved.read_bytes() == b"# hello"
    assert created[0]["doc_id"] == "doc_fixed"
    assert created[0]["file_ext"] == "md"
    assert created[0]["file_size"] == 7
    assert scheduled[0][0][:2] == ("doc_fixed", 7)


def test_upload_prefers_explicit_file_name(upload_env):
    settings, created, scheduled = upload_env

    resp = client.post(
        "/api/v1/knowledge-base/documents",
        files={"file": ("XPMKz6zl0j8W2a9ec9987d6ca4e2fecd4967d1cdb1d0.pdf", b"%PDF", "application/pdf")},
        data={"file_name": "高性价比人生指南(1).pdf"},
        headers=HEADERS,
    )

    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["file_name"] == "高性价比人生指南(1).pdf"
    assert created[0]["file_name"] == "高性价比人生指南(1).pdf"
    assert scheduled[0][0][4] == "高性价比人生指南(1).pdf"
    saved = settings.kb_upload_path / "7" / "doc_fixed" / "高性价比人生指南(1).pdf"
    assert saved.read_bytes() == b"%PDF"


def test_upload_explicit_file_name_strips_path(upload_env):
    _, created, scheduled = upload_env

    resp = client.post(
        "/api/v1/knowledge-base/documents",
        files={"file": ("hash.pdf", b"%PDF", "application/pdf")},
        data={"file_name": "../../高性价比人生指南(1).pdf"},
        headers=HEADERS,
    )

    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["file_name"] == "高性价比人生指南(1).pdf"
    assert created[0]["file_name"] == "高性价比人生指南(1).pdf"
    assert scheduled[0][0][4] == "高性价比人生指南(1).pdf"


@pytest.mark.parametrize("filename", ["a.pdf", "a.docx", "a.md", "a.txt"])
def test_upload_accepts_supported_extensions(upload_env, filename):
    resp = client.post(
        "/api/v1/knowledge-base/documents",
        files={"file": (filename, b"content", "application/octet-stream")},
        headers=HEADERS,
    )

    assert resp.json()["code"] == 0


def test_upload_rejects_unsupported_extension(upload_env):
    settings, created, scheduled = upload_env

    resp = client.post(
        "/api/v1/knowledge-base/documents",
        files={"file": ("a.doc", b"content", "application/msword")},
        headers=HEADERS,
    )

    body = resp.json()
    assert body["code"] == 4000
    assert "不支持" in body["message"]
    assert created == []
    assert scheduled == []
    if settings.kb_upload_path.exists():
        assert not any(p.is_file() for p in settings.kb_upload_path.rglob("*"))


def test_upload_rejects_empty_file(upload_env):
    resp = client.post(
        "/api/v1/knowledge-base/documents",
        files={"file": ("a.md", b"", "text/markdown")},
        headers=HEADERS,
    )

    body = resp.json()
    assert body["code"] == 4000
    assert "为空" in body["message"]


def test_upload_rejects_oversized_file(upload_env):
    settings, created, scheduled = upload_env

    resp = client.post(
        "/api/v1/knowledge-base/documents",
        files={"file": ("a.md", b"x" * (1024 * 1024 + 1), "text/markdown")},
        headers=HEADERS,
    )

    body = resp.json()
    assert body["code"] == 4000
    assert "超过" in body["message"] or "过大" in body["message"]
    assert created == []
    assert scheduled == []


def test_upload_requires_knowledge_base_config(monkeypatch, upload_env, tmp_path):
    monkeypatch.setattr(
        knowledge_base_service,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            dashscope_api_key="",
            kb_upload_dir=str(tmp_path / "kb-unconfigured"),
        ),
    )

    resp = client.post(
        "/api/v1/knowledge-base/documents",
        files={"file": ("a.md", b"content", "text/markdown")},
        headers=HEADERS,
    )

    assert resp.json()["code"] == 4007


def test_upload_sanitizes_filename_path(upload_env):
    settings, created, scheduled = upload_env

    resp = client.post(
        "/api/v1/knowledge-base/documents",
        files={"file": ("../../evil.md", b"content", "text/markdown")},
        headers=HEADERS,
    )

    assert resp.json()["code"] == 0
    assert created[0]["file_name"] == "evil.md"
    saved = settings.kb_upload_path / "7" / "doc_fixed" / "evil.md"
    assert saved.exists()
    assert not (settings.kb_upload_path.parent / "evil.md").exists()


def test_delete_document_succeeds(monkeypatch, tmp_path):
    fake = FakeDB().install(monkeypatch)
    fake.fetch_one_queue = [_doc_row()]
    fake.execute_queue = [(0, 1)]
    settings = _settings(tmp_path)
    file_path = settings.kb_upload_path / "7" / "doc_1" / "笔记.md"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("content", encoding="utf-8")
    store = FakeStore()
    monkeypatch.setattr(knowledge_base_service, "get_settings", lambda: settings)
    monkeypatch.setattr(knowledge_base_service, "build_vector_store", lambda *_: store)

    resp = client.delete("/api/v1/knowledge-base/documents/doc_1", headers=HEADERS)

    assert resp.json()["code"] == 0
    assert store.deleted == [(7, "doc_1")]
    assert not file_path.exists()


def test_delete_document_is_owner_scoped(monkeypatch):
    FakeDB().install(monkeypatch)

    resp = client.delete(
        "/api/v1/knowledge-base/documents/doc_other", headers=OTHER_HEADERS
    )

    assert resp.json()["code"] == 4040


def test_polling_reflects_status_transitions(monkeypatch):
    fake = FakeDB().install(monkeypatch)
    stats_processing = {
        "total_documents": 1,
        "ready_documents": 0,
        "processing_documents": 1,
        "failed_documents": 0,
        "total_chunks": 0,
    }
    stats_ready = {
        "total_documents": 1,
        "ready_documents": 1,
        "processing_documents": 0,
        "failed_documents": 0,
        "total_chunks": 17,
    }
    fake.fetch_one_queue = [stats_processing, stats_ready]
    fake.fetch_all_queue = [
        [_doc_row()],
        [_doc_row(status="ready", chunk_count=17)],
    ]

    first = client.get("/api/v1/knowledge-base", headers=HEADERS).json()["data"]
    second = client.get("/api/v1/knowledge-base", headers=HEADERS).json()["data"]

    assert first["documents"][0]["status"] == "processing"
    assert second["documents"][0]["status"] == "ready"
    assert second["stats"]["ready_documents"] == 1
    assert second["documents"][0]["chunk_count"] == 17
