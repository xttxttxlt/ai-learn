import pytest

from app.core.config import Settings
from app.llm.knowledge_base import EmbeddingConfigError, build_embeddings


def _settings(**kwargs):
    return Settings(_env_file=None, **kwargs)


def test_missing_api_key_raises_config_error():
    with pytest.raises(EmbeddingConfigError) as excinfo:
        build_embeddings(_settings(dashscope_api_key=""))

    assert "DASHSCOPE_API_KEY" in str(excinfo.value)


def test_disabled_switch_raises_config_error():
    with pytest.raises(EmbeddingConfigError):
        build_embeddings(
            _settings(dashscope_api_key="key", enable_knowledge_base=False)
        )


def test_invalid_batch_size_raises_config_error():
    with pytest.raises(EmbeddingConfigError) as excinfo:
        build_embeddings(
            _settings(dashscope_api_key="key", embedding_batch_size=0)
        )

    assert "批量" in str(excinfo.value)


def test_builds_openai_compatible_embeddings():
    embeddings = build_embeddings(
        _settings(
            dashscope_api_key="key",
            embedding_model="text-embedding-v4",
            embedding_dimensions=1024,
            embedding_batch_size=8,
            embedding_timeout=30,
            embedding_max_retries=2,
        )
    )

    assert embeddings.model == "text-embedding-v4"
    assert embeddings.dimensions == 1024
    assert embeddings.chunk_size == 8
    assert embeddings.check_embedding_ctx_length is False
    assert embeddings.request_timeout == 30
    assert embeddings.max_retries == 2
