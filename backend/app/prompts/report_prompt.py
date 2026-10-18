from langchain_core.prompts import ChatPromptTemplate

REPORT_SCHEMA_EXAMPLE = """{
  "accuracy": 80,
  "mastered_points": ["知识点1"],
  "weak_points": ["知识点2"],
  "three_line_summary": ["一句话总结1", "一句话总结2", "一句话总结3"],
  "advice": ["复习建议1", "复习建议2"],
  "share_quote": "今天我又闯过一个知识关卡"
}"""

_SYSTEM = (
    "你是一名学习复盘教练，擅长基于真实答题数据给出清晰、鼓励式但不空泛的复盘，"
    "语言适合移动端阅读。"
)

_USER_TEMPLATE = """请根据用户本次闯关答题记录，生成一份结构化复盘报告。

硬性要求：
1. 输出必须是合法 JSON，且只输出 JSON 本身，不要输出任何额外说明、Markdown 标记或代码块围栏。
2. 语言风格清晰、鼓励式，但不要空泛套话。
3. 分析必须基于下面提供的真实答题数据与统计结果，不要编造未出现的结论。
4. three_line_summary 恰好 3 句；advice 给 2 到 3 条可执行建议；share_quote 是一句可用于分享的学习金句。
5. accuracy、mastered_points、weak_points 已由上游统计给出，请与其保持一致，不要篡改数值。

输出 JSON 必须严格符合以下结构示例（字段名与类型保持一致）：
{schema_example}

用户主题：{topic}
统计结果（正确率/掌握点/薄弱点，以此为准）：{score_summary}
题库数据：{quiz_json}
答题记录：{answer_records}"""

REPORT_PROMPT_V1 = ChatPromptTemplate.from_messages(
    [
        ("system", _SYSTEM),
        ("user", _USER_TEMPLATE),
    ]
)
