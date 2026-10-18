import re

MAX_INPUT_LEN = 4000


def clean_user_input(raw: str | None) -> str:
    """清洗用户输入：统一换行、折叠空白、去首尾、超长截断。"""
    if raw is None:
        return ""
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()
    if len(text) > MAX_INPUT_LEN:
        text = text[:MAX_INPUT_LEN].rstrip()
    return text
