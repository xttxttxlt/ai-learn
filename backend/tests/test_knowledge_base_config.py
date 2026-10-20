import pytest

from app.core.config import BASE_DIR, Settings

_KB_ENV_KEYS = (
    "ENABLE_KNOWLEDGE_BASE",
    "DASHSCOPE_API_KEY",
    "EMBEDDING_BASE_URL",
    "EMBEDDING_MODEL",
    "EMBEDDING_DIMENSIONS",
    "EMBEDDING_BATCH_SIZE",
    "EMBEDDING_TIMEOUT",
    "EMBEDDING_MAX_RETRIES",
    "CHROMA_PERSIST_DIR",
    "KB_UPLOAD_DIR",
    "KB_MAX_FILE_MB",
    "KB_CHUNK_SIZE",
    "KB_CHUNK_OVERLAP",
    "KB_MAX_CHUNKS_PER_DOC",
    "KB_RETRIEVAL_TOP_K",
    "KB_INGESTION_CONCURRENCY",
)


@pytest.fixture(autouse=True)
def _clean_kb_env(monkeypatch):
    for key in _KB_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_knowledge_base_defaults():
    settings = Settings(_env_file=None)

    assert settings.enable_knowledge_base is True
    assert settings.dashscope_api_key == ""
    assert settings.embedding_base_url == (
        "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    assert settings.embedding_model == "text-embedding-v4"
    assert settings.embedding_dimensions == 1024
    assert settings.embedding_batch_size == 8
    assert settings.embedding_timeout == 30
    assert settings.embedding_max_retries == 2
    assert settings.chroma_persist_dir == "data/chroma"
    assert settings.kb_upload_dir == "data/knowledge_base"
    assert settings.kb_max_file_mb == 10
    assert settings.kb_chunk_size == 800
    assert settings.kb_chunk_overlap == 100
    assert settings.kb_max_chunks_per_doc == 2000
    assert settings.kb_retrieval_top_k == 4
    assert settings.kb_ingestion_concurrency == 2


def test_relative_dirs_resolve_against_backend_dir():
    settings = Settings(
        _env_file=None,
        chroma_persist_dir="data/chroma",
        kb_upload_dir="data/knowledge_base",
    )

    assert settings.chroma_persist_path == BASE_DIR / "data" / "chroma"
    assert settings.kb_upload_path == BASE_DIR / "data" / "knowledge_base"


def test_absolute_dirs_are_kept(tmp_path):
    chroma = tmp_path / "chroma"
    upload = tmp_path / "upload"
    settings = Settings(
        _env_file=None,
        chroma_persist_dir=str(chroma),
        kb_upload_dir=str(upload),
    )

    assert settings.chroma_persist_path == chroma
    assert settings.kb_upload_path == upload


def test_knowledge_base_ready_requires_switch_and_key():
    assert Settings(_env_file=None, dashscope_api_key="").knowledge_base_ready is False
    assert (
        Settings(_env_file=None, dashscope_api_key="ds-key").knowledge_base_ready is True
    )
    assert (
        Settings(
            _env_file=None,
            dashscope_api_key="ds-key",
            enable_knowledge_base=False,
        ).knowledge_base_ready
        is False
    )


def test_max_file_bytes():
    settings = Settings(_env_file=None, kb_max_file_mb=10)
    assert settings.kb_max_file_bytes == 10 * 1024 * 1024
