"""Smoke 测试：验证 LangChain 1.x 下 ChatOpenAI 构造与 with_structured_output(json_mode)
的 API 兼容性。不发起任何网络请求。"""

from app.llm.langchain_factory import build_chat_model
from app.llm.quiz_chain import build_quiz_chain


def test_build_chat_model_accepts_deepseek_params():
    llm = build_chat_model(temperature=0.4, max_tokens=1024)
    # 关键参数已正确落到模型上
    assert llm.model_name == "deepseek-flash"
    assert float(llm.temperature) == 0.4


def test_build_quiz_chain_structured_output_no_network():
    llm = build_chat_model(temperature=0.4, max_tokens=1024)
    chain = build_quiz_chain(llm)
    assert chain is not None
