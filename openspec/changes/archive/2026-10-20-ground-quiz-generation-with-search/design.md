# Design

## Context

动机见 `proposal.md - Why`。当前出题链路（`backend/app/llm/quiz_chain.py` + `backend/app/services/quiz_service.py`）是 `ChatPromptTemplate | llm.with_structured_output(QuizOutputSchema, method="json_mode", include_raw=True)`，只把清洗后的用户文本喂给 DeepSeek flash，无外部知识来源；Prompt 还显式允许“基于常识合理补充”。用户输入可能是一句话、一段文本，**也可能是一个网页链接**。约束：

- 大模型走 OpenAI 兼容接口对接 DeepSeek flash，非 thinking 模式（`langchain_factory.build_chat_model`）。
- DeepSeek 官方仅文档化 `response_format={"type":"json_object"}`，未承诺 strict `json_schema`；支持工具调用（function calling）。
- 现有出题服务已有五级兜底与三级校验（题量、选项、答案一致性），必须保留。
- 前端 Taro 4.3 + React；`REQUEST_TIMEOUT=60000`；出题结果经 `setCurrentQuiz` 存本地，历史回看走 `getQuizDetail`。
- `quiz_sessions` 表当前列：quiz_id/user_id/title/summary/user_input/questions_json/created_at。
- 本机直连海外服务可能需走代理（`127.0.0.1:7897`）。

**`langchain-tavily` 官方工具关键事实（已核对官方文档）**：
- `TavilySearch`（工具名默认 `tavily_search`）：实例化参数含 `max_results`(默认5)、`topic`(general)、`include_answer`(False)、`include_raw_content`(False)、`search_depth`(basic)、`time_range`、`include_domains`/`exclude_domains`、`country`。**调用时可改**：`query`(必填)、`search_depth`、`time_range`、`include_domains`、`exclude_domains`、`include_images`、`topic`、`start_date`/`end_date`。**仅实例化可设**：`include_answer`、`include_raw_content`、`max_results`、`country`。返回 JSON 字符串，含 `results[]`（`title/url/content/score/raw_content`）与 `answer`。
- `TavilyExtract`（工具名默认 `tavily_extract`）：实例化参数含 `extract_depth`(basic/advanced)、`include_images`、`include_favicon`、`format`(markdown/text)。调用入参 `urls`(list，必填)，可覆盖 `extract_depth`/`include_images`。返回 `results[]`（`url/raw_content/images`）、`failed_results[]`、`response_time`。

## Goals / Non-Goals

**Goals:**
- 用 LangChain Agent（`create_agent`）+ `langchain-tavily` 的搜索与抽取工具，让出题前联网接地，消除“过时/编造/选错领域”的题目。
- 接地支持两种来源：关键词搜索（`TavilySearch`）与网页 URL 正文抽取（`TavilyExtract`）；用户输入含 URL 时可直接抓取整页。
- 采用**多实例工具策略**：把搜索/抽取注册成多个具名实例并全部交给 Agent，由模型自主决定何时调哪个、并动态选择参数（深度、信息量、范围），兼顾国内外用户与不同复杂度主题。
- 对多义主题自动判定单一解读并显式标注（interpretation），把真实来源（sources）透出到前端与历史。
- 接地不可用/失败时无缝回退现有 v1 出题链，主流程零中断；保留结构化契约、三级校验、五级兜底。

**Non-Goals:**
- 不做 PDF/Word/视频解析（网页 URL 抽取在范围内）、不做私有知识库向量 RAG。
- 不做“交互式歧义澄清”（不增加前后端往返）；本次仅自动判定 + 标注。
- 不改报告链、评分、金币、用户系统；不引入 LangGraph 自定义图或多 Agent。

## Decisions

### 决策 1：Agent 框架用 LangChain 1.0 `create_agent`
- **选择**：`from langchain.agents import create_agent`；阶段一用 `create_agent(model=llm, tools=[web_search_brief, web_search_full, web_extract], system_prompt=RESEARCH_PROMPT_V2)`（**不挂 response_format**）组装“研究 Agent”；`agent.invoke({"messages":[{"role":"user","content":...}]}, config={"recursion_limit": N})`；从 `result["messages"]` 取“研究简报”文本并确定性抽取来源。结构化题库由阶段二的 json_mode 链产出（见决策 2）。
- **理由**：用户选定 agentic 方案；`create_agent` 是 1.0 现行稳定入口，内置工具循环，模型可自主决定何时调哪个工具。
- **备选**：非 Agent 管线（用户已否决）；旧版 `create_openai_tools_agent`+`AgentExecutor`（旧路径）；`langgraph.prebuilt.create_react_agent`（更底层）。
- **影响**：`requirements.txt` 需 `langchain>=1.0`、`langchain-tavily`、`tavily-python`；须回归现有测试。

### 决策 2：接地走“两阶段”——研究 Agent + json_mode 结构化链（而非单 Agent ToolStrategy）
- **选择**：阶段一 `create_agent`（仅挂搜索/抽取工具、**不挂 response_format**）让模型自主检索/抽取，稳定地以一段“研究简报”**纯文本**收尾；阶段二把简报 + 用户内容喂给 `with_structured_output(QuizOutputSchema, method="json_mode", include_raw=True)`（与 v1 相同的稳定机制，见 `build_grounded_chain`）产出题库（含 interpretation）。来源从阶段一的工具消息 artifact 确定性抽取。
- **理由（实测调整）**：原计划的单 Agent `ToolStrategy(QuizOutputSchema)` 在 DeepSeek 上**不稳定**——实测会偶发地不调用结构化输出工具（直接返回文本收尾）或超出 recursion_limit，导致 `structured_response` 为空。两阶段把“工具调用”限定在研究阶段（以纯文本收尾，稳定），把“结构化输出”交给 DeepSeek 已验证可靠的 json_mode，从根本上消除该不确定性；阶段二仍复用现有重试与三级校验。
- **备选**：保留 ToolStrategy + 多次重试（仍概率性失败，成本高、延迟大，可能触发前端超时）；`ProviderStrategy`（DeepSeek 未承诺原生 strict json_schema，风险更高）。

### 决策 3：多实例工具策略（核心）
- **选择**：注册 3 个具名工具实例，全部交给 Agent：
  - `web_search_brief` = `TavilySearch(search_depth="basic", include_raw_content=False, include_answer=True, max_results=5, topic="general")`：简单主题，返回摘要 + answer，轻量快速。
  - `web_search_full` = `TavilySearch(search_depth="advanced", include_raw_content=True, include_answer=True, max_results=3, topic="general")`：复杂主题，结果直接含正文（`raw_content`），实例数更小防 token 爆。
  - `web_extract` = `TavilyExtract(extract_depth="advanced", format="markdown", include_images=False)`：用户给了 URL（或搜索定位到权威 URL）时，抓取整页正文。
- **理由**：`include_raw_content`/`include_answer`/`max_results`/`country` **仅实例化可设**，无法在调用时切换。要让模型“动态选择”这些维度，只能预置成不同具名实例供其挑选；而 `search_depth`/`time_range`/`include_domains`/`exclude_domains` 调用时可改，交给模型逐次微调。这样“复杂→全文、简单→摘要、动态条数”都能由模型自主决策。
- **命名**：`TavilySearch` 默认工具名固定为 `tavily_search`，多实例会重名 → 必须为每个实例覆盖唯一 `name`（构造入参 `name=` 或实例属性 / `model_copy(update={"name":...})`）。**验证项**：确认 `langchain-tavily` 工具支持改名；若不支持，则用薄 `@tool` 封装委托到官方工具（仍满足“使用官方两个工具”），并在封装里设唯一名与 `response_format="content_and_artifact"`。
- **备选**：只给单个 `TavilySearch`+`TavilyExtract`（无法覆盖 include_raw_content/max_results 的动态差异，达不到用户要求）。

### 决策 4：Agent 自主选择工具与参数（靠 Prompt v2 引导）
- 系统提示中列出各工具用途与选择启发式：
  1. 输入含 URL → 先用 `web_extract` 抓正文；必要时再 `web_search_*` 补充背景。
  2. 关键词/主题且为简单概念 → `web_search_brief`。
  3. 主题复杂、或摘要不足以准确出题 → `web_search_full`；或先 `web_search_brief` 找到权威 URL 再 `web_extract`。
  4. 调用时按主题的地区/时效/站点倾向动态设置 `search_depth`、`time_range`、`include_domains`/`exclude_domains`。
  5. 允许有限多轮（受 `recursion_limit` 约束），够用即止；最终基于获取到的事实出题并给出 interpretation。

### 决策 5：兼顾国内外（“城市范围”的落地解释）
- Tavily **无城市级参数**。地区/范围控制落在：`country`（实例化级）、`topic`（general/news）、`time_range`、`include_domains`/`exclude_domains`（调用级）。
- **方案**：默认 `country=None`（全球），由模型在调用时动态调 `time_range` 与域名白/黑名单收敛范围；把“城市范围”理解为“国家/地区 + 域名 + 时间范围”。若确需地区定向，可追加具名地区实例（如国内/国际各一）——列为 Open Question，避免实例爆炸。

### 决策 6：sources 确定性提取（兼容搜索与抽取）
- 遍历 `result["messages"]` 的 `ToolMessage`，按工具名取 artifact：
  - `web_search_*` → `artifact["results"]` 抽 `{title,url,score}`；
  - `web_extract` → `artifact["results"]` 抽 `{url, raw_content}`，title 取页面标题，缺省用 URL/host。
- 合并后按 url 去重、排序（抽取来源优先、搜索按 score），截断前 N 条。**不由模型输出 URL**，杜绝编造。
- 若 `langchain-tavily` 工具消息未暴露结构化 artifact，则改用决策 3 的薄 `@tool(response_format="content_and_artifact")` 封装，自行把原始结果 dict 放进 artifact（实施首步验证）。

### 决策 7：interpretation 由模型产出（仅后端内部使用）
- `QuizOutputSchema` 增 `interpretation: str`，系统提示要求模型在接地后声明“本次按哪个领域/解读出题”。它是标签而非事实，幻觉风险低。
- 作用：促使 Agent 在出题前先锁定单一领域（提升接地质量），并随题库落库备查；**不在前端展示**——用户通过“参考来源”核对接地即可。

### 决策 8：优雅降级与特性开关
- 新增 `quiz_grounding_enabled`（默认 true）与 `tavily_api_key`。仅当开关开启且 key 非空走 Agent；Agent 任何异常（检索/抽取失败、超时、结构化失败、超 `recursion_limit`）或 key 缺失 → 回退现有 `build_quiz_chain`（v1），`grounded=False`、`sources=[]`、`interpretation=""`。
- `web_extract` 的 `failed_results` 不视为整体失败：可回退到搜索摘要或 v1；记录日志。

### 决策 9：Prompt v2 与 v1 并存
- 新增 `QUIZ_PROMPT_V2`（Agent 系统提示，含决策 4 的工具选择与参数引导）；保留 v1 供降级链使用（方案设计 §8.7 版本化）。

### 决策 10：数据模型与持久化
- `Quiz` 增 `interpretation: str=""`、`sources: list[Source]=[]`、`grounded: bool=False`；新增 `Source{title,url,score?}`（可加 `kind: "search"|"extract"` 便于前端区分，可选）。`QuizOutputSchema` 增 `interpretation`。
- DB：`quiz_sessions` 增 `interpretation TEXT NULL`、`sources_json JSON NULL`、`grounded TINYINT(1) NOT NULL DEFAULT 0`（均加中文 COMMENT）。同步 `sql/init_mysql.sql` + 新增迁移脚本（additive/可空，向后兼容）。
- 仓储/服务：`insert_quiz_session` 增参；`persist_quiz` 落新字段；`history_service.get_detail` 回填；`QuizDetail`（`models/user.py`）与前端类型增字段。

### 决策 11：循环、延迟与 token 控制
- `recursion_limit`（默认约 8）限工具轮次；`web_search_full` 的 `max_results` 调小、`raw_content` 与 `web_extract` 正文在工具摘要（digest）里按每条上限截断（如每条前 K 字符），防止 token 爆与成本飙升。
- 模型单次 `timeout=30s` 不变；路由已在 `run_in_threadpool`；前端 `REQUEST_TIMEOUT=60000` 维持，必要时上调；首页/闯关 loading 文案体现“检索/抓取 + 出题”。

## Risks / Trade-offs

- [多个 `TavilySearch` 实例默认同名 `tavily_search` 冲突] → 覆盖唯一 `name`；先验证 `langchain-tavily` 是否支持改名，否则用薄 `@tool` 封装委托官方工具。
- [全文检索/网页抽取正文导致 token 爆炸、成本与延迟上升] → `web_search_full` 小 `max_results`、digest 每条截断、`recursion_limit` 限轮次；简单主题走 brief。
- [`TavilyExtract` 对部分 URL 抽取失败（`failed_results`）] → 回退搜索摘要或 v1；记录 failed_results，不中断。
- [DeepSeek 多工具选择/参数决策可靠性未知] → 系统提示写清工具用途与选择规则；观测接地成功率与工具调用轨迹；选择混乱时收紧提示或降级。
- [`langchain-tavily` 工具返回结构（字符串 vs artifact）不确定] → 实施首步写连通性脚本，分别验证 `TavilySearch().invoke({"query":...})` 与 `TavilyExtract().invoke({"urls":[...]})` 返回结构，再据实决定直接解析或用 `content_and_artifact` 封装。
- [LangChain 升级 1.0 回归] → 升级后先跑现有 `pytest`；`with_structured_output`/`ChatPromptTemplate`/report_chain 在 1.0 仍兼容。
- [Tavily 海外访问需代理] → 由环境变量/httpx 客户端透传代理；不可达自动降级 v1。
- [Tavily 无城市级地区参数] → 以 `country`/`time_range`/域名过滤近似；已在决策 5 说明，地区定向实例列为 Open Question。

## Migration Plan

1. 加依赖（`langchain>=1.0`、`langchain-tavily`、`tavily-python`）与配置（`TAVILY_API_KEY`、`QUIZ_GROUNDING_ENABLED`、各实例 `max_results`/`search_depth`/`extract_depth`、`TAVILY_COUNTRY`、`QUIZ_AGENT_RECURSION_LIMIT`、digest 截断长度）。
2. 先做连通性验证脚本（含代理）：分别验证 `TavilySearch`（brief/full）与 `TavilyExtract` 的返回结构与工具改名可行性，再落地工具封装与 Agent。
3. DB：新增迁移脚本 `ALTER TABLE quiz_sessions ADD COLUMN ...`（可空/带默认）；同步 `init_mysql.sql`。回滚：列为附加可空，`QUIZ_GROUNDING_ENABLED=false` 即可停用接地；确需回滚再 `DROP COLUMN`。
4. 后端接线：v2 Prompt + 多实例工具 Agent + 来源抽取 + 降级；扩展 `Quiz`/响应/持久化/历史详情。
5. 前端：类型扩展 + 闯关页展示参考来源（可区分搜索/网页）+ 回看页展示来源（“本次解读”仅后端内部判定，不展示）。
6. 灰度：先 `QUIZ_GROUNDING_ENABLED=false` 部署验证无回归，再配置 key 开启，观测接地成功率、工具选择合理性与延迟/成本。

## Open Questions

- 是否需要追加“国内/国际”地区定向具名实例，还是仅靠调用时域名/时间过滤 + 可配 `country`？（不影响主结构，可上线后按效果定）
- 是否把 `search_depth`/`max_results` 通过封装进一步暴露为模型可控入参（更灵活但更复杂）？
- digest 每条截断长度、extract 来源的标题/排序与前端是否展示来源类型（search/网页）等 UI 细节。
- 生产环境 Tavily 的代理/网络出口配置方式（降级路径已覆盖不可达）。
