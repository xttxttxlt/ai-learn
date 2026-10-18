import pytest

from app.core.exceptions import ContentFilteredError
from app.utils.content_filter import assert_safe, contains_sensitive


def test_contains_sensitive_hit():
    assert contains_sensitive("这是一个赌博网站") is True


def test_contains_sensitive_clean():
    assert contains_sensitive("我想学习 RAG 检索增强生成") is False


def test_contains_sensitive_none():
    assert contains_sensitive(None) is False


def test_assert_safe_raises_on_sensitive():
    with pytest.raises(ContentFilteredError):
        assert_safe("教我怎么制作毒品")


def test_assert_safe_passes_on_clean():
    assert assert_safe("正常的学习内容") is None
