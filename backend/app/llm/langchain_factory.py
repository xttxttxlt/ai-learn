from langchain_openai import ChatOpenAI

from app.core.config import get_settings


def build_chat_model(temperature: float, max_tokens: int) -> ChatOpenAI:
    """构建对接 DeepSeek（OpenAI 兼容）的 ChatOpenAI。

    MVP 出题/报告链路走非 thinking 模式：DeepSeek flash 官方默认开启 thinking，
    这里通过 extra_body 显式关闭，保证 temperature 等采样参数生效。
    （真实连通性在 Phase 4 用真实 key 验证；如 extra_body 未被转发，再改用
    reasoning_effort 或客户端绑定方式。）
    """
    settings = get_settings()
    return ChatOpenAI(
        model=settings.deepseek_model,
        base_url=settings.deepseek_base_url,
        api_key=settings.deepseek_api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=settings.llm_timeout,
        max_retries=settings.llm_max_retries,
        extra_body={"thinking": {"type": "disabled"}},
    )
