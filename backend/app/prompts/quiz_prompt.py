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


# ===== V2：联网接地出题（两阶段）=====
# 阶段一：研究 Agent（挂多个 Tavily 工具，自主检索/抽取），产出一段“研究简报”纯文本。
# 阶段二：把研究简报喂给稳定的 json_mode 结构化链产出题库（含 interpretation）。
# 说明：DeepSeek 对“工具调用式结构化输出(ToolStrategy)”支持不稳定，故出题的结构化
#       统一走 json_mode（v1 已验证可靠），Agent 只负责研究与来源采集。

# 结构化输出示例（含 interpretation），阶段二 partial 注入
QUIZ_V2_SCHEMA_EXAMPLE = """{
  "title": "学习主题",
  "summary": "本次题库的主题摘要",
  "interpretation": "本次出题所选定的领域/角度解读；主题多义时说明按哪个领域出题",
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

# 阶段一：研究 Agent 的系统提示（纯字符串，供 create_agent 的 system_prompt 使用）
RESEARCH_PROMPT_V2 = """你是一名联网研究助手，具备关键词检索与网页抽取能力，只为“出题”收集最新、权威的事实依据，本身不出题。

可用工具（由你自主决定何时调用哪个、调用几次）：
- web_search_brief：按关键词搜索，返回多条结果的标题/链接/摘要，适合简单概念、快速确认。
- web_search_full：按关键词搜索并返回结果正文，信息更全、条数更少，适合复杂或冷门主题、或摘要不足时。
- web_extract：给定一个或多个 URL，抓取整页正文；当用户输入包含网页链接，或需要取搜索定位到的权威页面全文时使用。
可依据主题的时效/地区/站点倾向，动态设置 search_depth、time_range、include_domains、exclude_domains 等参数。

工作方式：
1. 判断用户输入类型：若包含网页 URL，优先用 web_extract 抓取正文；否则用搜索工具检索。
2. 若主题可能新、冷门或多义（品牌/产品/新兴概念等），务必先检索，锁定单一最相关的领域/解读。
3. 检索到足够信息即停止，不要无谓地反复搜索。
4. 工具调用总数不超过 10 次；达到上限后不要再调用工具，直接依据已获得的信息输出简报。

最终只输出一段中文“研究简报”（纯文本，不要出题、不要输出 JSON），包含三部分：
- 【解读】本次采用的领域/解读（若主题多义，说明选了哪个、依据是什么）。
- 【关键事实】用于出题的核心事实要点，尽量标注出处 URL。
- 【接地情况】若检索/抽取失败或信息不足，如实说明。"""


# 阶段一（知识库版）：首页 Agent 在个人知识库与联网间自主路由；文档模式仅用当前文档。
RESEARCH_PROMPT_WITH_KB = """你是一名研究助手，可以使用当前用户的个人知识库检索，以及（在提供时）联网检索与网页抽取，只为“出题”收集真实、可追溯的事实依据，本身不出题。

可用工具（由你自主决定何时调用哪个、调用几次）：
- search_knowledge_base：检索当前用户的个人知识库（用户上传的文档），返回文档名、页码、相关度与分块摘要。若工具说明为“仅限当前文档”，它只会检索本次选定的当前文档。
- web_search_brief：按关键词联网搜索，返回多条结果的标题/链接/摘要，适合简单概念、快速确认。
- web_search_full：按关键词联网搜索并返回结果正文，信息更全、条数更少，适合复杂或冷门主题。
- web_extract：给定一个或多个 URL，抓取整页正文；当用户输入包含网页链接，或需要取搜索定位到的权威页面全文时使用。

工作方式：
1. 如果本次只提供 search_knowledge_base（文档一键闯关）：必须仅使用个人知识库工具，禁止使用联网；只依据当前文档的分块事实，信息不足时如实说明，不得用常识或泛化知识补全。
2. 如果同时提供联网工具（首页出题）：自主选择来源。内部资料、私有内容、题库/培训资料等主题优先检索个人知识库；依赖最新公开信息、或知识库没有覆盖时使用联网检索；必要时可混合使用两种来源。若 search_knowledge_base 返回“无足够相关内容”或“无相关结果”，说明知识库未覆盖该主题，不得继续引用知识库结果，应改用联网检索或按通用知识出题。
3. 每个关键事实都要标注来源类型：知识库来源标注文档名与页码（如有），联网来源标注 URL。
4. 检索到足够信息即停止，不要无谓地反复检索。
5. 工具调用总数（知识库与联网合计）不超过 10 次；达到上限后不要再调用工具，直接依据已获得的信息输出简报。

最终只输出一段中文“研究简报”（纯文本，不要出题、不要输出 JSON），包含三部分：
- 【解读】本次采用的领域/解读（若主题多义，说明选了哪个、依据是什么）。
- 【关键事实】用于出题的核心事实要点，逐条标注出处（知识库文档名/页码或 URL）。
- 【接地情况】若检索/抽取失败或信息不足，如实说明。
不得编造任何事实、文档名、页码或 URL；没有检索到的内容不得写入简报。"""


def format_research_user_message(user_input: str) -> str:
    """构造研究 Agent 的用户消息。"""
    return (
        "请就以下学习内容研究，并按规定输出研究简报"
        f"（内容可能是文本，也可能包含网页链接）：\n{user_input}"
    )


# 阶段二：接地出题（json_mode 结构化），必须基于研究简报、禁止编造
_GROUNDED_SYSTEM = (
    "你是一名专业的 AI 学习教练，擅长把学习内容拆解成结构化、可讲解、适合小程序闯关答题的题目。"
    "你已获得一份研究简报（来自联网检索、网页抽取或个人知识库检索），必须严格依据简报中的事实出题。"
)

_GROUNDED_USER_TEMPLATE = """请基于“研究简报”和用户学习内容，生成一组用于小程序闯关答题的题目。

硬性要求：
1. 输出必须是合法 JSON，且只输出 JSON 本身，不要输出任何额外说明、Markdown 标记或代码块围栏。
2. 题目总数为 {question_count} 题。
3. 题型需覆盖单选题、多选题、判断题；以单选为主。
4. 难度要求：{difficulty_instruction}
5. 每道题必须包含字段：id、type、stem、options、answer、explanation、knowledge_point、difficulty。
6. type 取值只能是 single（单选）、multiple（多选）、judge（判断）。
7. answer 是正确选项 key 组成的数组；单选题与判断题 answer 只含 1 个 key，多选题含 2 个或以上。
8. 判断题的 options 固定为两项：key 为 A 表示“正确”，key 为 B 表示“错误”。
9. explanation 必须通俗、简洁、适合初学者与移动端阅读，答错时也能讲清错因。
10. 题干、选项、答案与讲解必须基于“研究简报”中的事实，来源可以是联网检索、网页抽取或个人知识库检索；严禁编造简报中无从佐证的事实、数据、文档名、页码或链接。
11. interpretation 字段：写明本次出题采用的领域/解读（依据研究简报的【解读】）；主题明确时可复述主题；若简报表明接地不足，请如实说明。

输出 JSON 必须严格符合以下结构示例（字段名与类型保持一致，务必包含 interpretation）：
{schema_example}

研究简报（联网检索/网页抽取/个人知识库检索所得）：
{research}

用户学习内容如下：
{user_input}"""

QUIZ_GROUNDED_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", _GROUNDED_SYSTEM),
        ("user", _GROUNDED_USER_TEMPLATE),
    ]
)
