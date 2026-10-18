"""基础敏感词过滤（MVP stub）。

仅做本地词表命中检测，后续可替换为正式词库或云端内容安全审核。
"""

from app.core.exceptions import ContentFilteredError

# 极简示例词表，覆盖明显违规类目；正式环境应接入完整词库。
_SENSITIVE_WORDS: tuple[str, ...] = (
    "赌博",
    "博彩",
    "毒品",
    "制毒",
    "枪支弹药",
    "暴恐",
    "恐怖袭击",
    "自杀教程",
    "色情",
    "裸聊",
)


def contains_sensitive(text: str | None) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(word.lower() in lowered for word in _SENSITIVE_WORDS)


def assert_safe(text: str | None) -> None:
    if contains_sensitive(text):
        raise ContentFilteredError()
