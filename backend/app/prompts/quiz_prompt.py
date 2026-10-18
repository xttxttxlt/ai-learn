from langchain_core.prompts import ChatPromptTemplate

# 以变量形式注入的 JSON 结构示例，避免在模板里转义大量花括号。
SCHEMA_EXAMPLE = """{
  "title": "学习主题",
  "summary": "本次题库的主题摘要",
  "questions": [
    {
      "id": "q1",
      "type": "single",
      "stem": "题干文本",
      "options": [
        {"key": "A", "text": "选项A"},
        {"key": "B", "text": "选项B"}
      ],
      "answer": ["A"],
      "explanation": "详细讲解",
      "knowledge_point": "知识点标签",
      "difficulty": "easy"
    }
  ]
}"""

_SYSTEM = (
    "你是一名专业的 AI 学习教练，擅长把任意学习内容拆解成结构化、可讲解、"
    "适合小程序闯关答题的题目。"
)

_USER_TEMPLATE = """请根据用户提供的学习内容，生成一组用于小程序闯关答题的题目。

硬性要求：
1. 输出必须是合法 JSON，且只输出 JSON 本身，不要输出任何额外说明、Markdown 标记或代码块围栏。
2. 题目总数为 {question_count} 题。
3. 题型需覆盖单选题、多选题、判断题；当题量为 5 时，比例为 3 道单选 + 1 道多选 + 1 道判断。
4. 难度要求：{difficulty_instruction}
5. 每道题必须包含字段：id、type、stem、options、answer、explanation、knowledge_point、difficulty。
6. type 取值只能是 single（单选）、multiple（多选）、judge（判断）。
7. answer 是正确选项 key 组成的数组；单选题与判断题 answer 只含 1 个 key，多选题含 2 个或以上。
8. 判断题的 options 固定为两项：key 为 A 表示“正确”，key 为 B 表示“错误”。
9. explanation 必须通俗、简洁、适合初学者与移动端阅读，答错时也能讲清错因。
10. 如果用户输入过短，可基于常识合理补充，但不要偏离主题。

输出 JSON 必须严格符合以下结构示例（字段名与类型保持一致）：
{schema_example}

用户学习内容如下：
{user_input}"""

QUIZ_PROMPT_V1 = ChatPromptTemplate.from_messages(
    [
        ("system", _SYSTEM),
        ("user", _USER_TEMPLATE),
    ]
)
