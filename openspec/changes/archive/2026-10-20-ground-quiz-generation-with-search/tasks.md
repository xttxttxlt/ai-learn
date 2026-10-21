# Tasks

## 1. 依赖与配置

- [x] 1.1 在 `backend/requirements.txt` 增加 `langchain>=1.0`、`langchain-tavily`、`tavily-python`；验证 `pip install -r requirements.txt` 成功且 `python -c "import langchain, langchain_tavily, tavily; from langchain_tavily import TavilySearch, TavilyExtract"` 无报错。
- [x] 1.2 升级后立即跑现有后端测试确认无回归：`cd backend && pytest`，`test_quiz_api`/`test_report_api`/`test_prompt_contract` 全绿。
- [x] 1.3 在 `backend/.env.example` 与 `backend/app/core/config.py` 增加：`TAVILY_API_KEY`、`ENABLE_WEB_SEARCH`(默认 true)、`TAVILY_SEARCH_BRIEF_MAX_RESULTS`(默认5)、`TAVILY_SEARCH_FULL_MAX_RESULTS`(默认3)、`TAVILY_SEARCH_FULL_DEPTH`(默认 advanced)、`TAVILY_EXTRACT_DEPTH`(默认 advanced)、`TAVILY_EXTRACT_FORMAT`(默认 markdown)、`TAVILY_COUNTRY`(默认空=全球)、`QUIZ_AGENT_RECURSION_LIMIT`(默认8)、`QUIZ_DIGEST_MAX_CHARS`(单条正文截断，默认如 2000)，均带默认值与中文注释；验证 `get_settings()` 能读到新字段。

## 2. 工具连通性验证与多实例封装

- [x] 2.1 写一次性连通性脚本（含代理），分别调用 `TavilySearch().invoke({"query":"Harness Engineering"})` 与 `TavilyExtract().invoke({"urls":["<某真实网页>"]})`，打印返回结构；验证 search 返回 `results[].{title,url,content,score,raw_content}`、extract 返回 `results[].{url,raw_content}` 与 `failed_results`，并确认工具消息是否携带结构化 artifact（脚本仅用于验证，不纳入主流程）。
- [x] 2.2 验证 `TavilySearch`/`TavilyExtract` 实例能否覆盖唯一 `name`（构造入参或属性/`model_copy`）；若不能，确定改用薄 `@tool(response_format="content_and_artifact")` 封装委托官方工具的方案。
- [x] 2.3 实现 `backend/app/llm/search_tools.py`：构建三个具名工具实例——`web_search_brief`(TavilySearch basic, include_raw_content=False, include_answer=True, max_results=brief)、`web_search_full`(TavilySearch advanced, include_raw_content=True, include_answer=True, max_results=full)、`web_extract`(TavilyExtract advanced, format=markdown)；如 2.2 结论需要则用薄封装并做 digest 截断（每条 ≤ `QUIZ_DIGEST_MAX_CHARS`）与 artifact 保留。单测 mock 底层，验证三工具名称唯一、摘要格式、artifact 结构、截断生效。

## 3. 出题 Prompt v2 与输出 Schema

- [x] 3.1 在 `backend/app/prompts/quiz_prompt.py` 新增 `QUIZ_PROMPT_V2`（Agent 系统提示）：说明三类工具用途与选择启发式（URL→抽取；简单→brief；复杂→full 或先搜后抽）、调用时可动态设 `search_depth`/`time_range`/`include_domains`/`exclude_domains`、先接地再基于事实出题、禁止编造、判定单一解读并输出含 `interpretation` 的结构化 JSON；保留 v1。扩展 `test_prompt_contract` 验证模板可导入、变量齐全。
- [x] 3.2 在 `backend/app/llm/output_schemas.py` 的 `QuizOutputSchema` 增加 `interpretation: str`；验证 Schema 可实例化并含新字段。

## 4. 出题 Agent 链与来源抽取

- [x] 4.1 新增 `backend/app/llm/quiz_agent.py` 的 `build_research_agent(llm, tools)`，用 `create_agent(model=llm, tools=[web_search_brief, web_search_full, web_extract], system_prompt=RESEARCH_PROMPT_V2)`（阶段一：只挂工具、不强制结构化输出，稳定以“研究简报”文本收尾）。**实测调整**：原设计的单 Agent `ToolStrategy(QuizOutputSchema)` 在 DeepSeek 上偶发不产出 structured_response，故改为两阶段——结构化题库由阶段二 `build_grounded_chain`(json_mode) 产出。单测验证 Agent 离线可编译、`extract_research_text` 取简报、`config={"recursion_limit": N}` 传入。
- [x] 4.2 实现来源抽取工具函数：遍历 `result["messages"]` 的 `ToolMessage`，按工具名分别解析 search（`results[].{title,url,score}`）与 extract（`results[].{url,raw_content}`，title 缺省用 URL/host）→ 合并、按 url 去重、排序（extract 优先、search 按 score）、截断前 N；单测覆盖去重、空结果、无 artifact、search+extract 混合、extract 全部 failed 场景，验证不编造 URL。

## 5. 出题服务改造与降级

- [x] 5.1 改造 `backend/app/services/quiz_service.py` 的 `generate_quiz`：当 `quiz_grounding_enabled` 且 `tavily_api_key` 非空时构建三工具 Agent 走接地链，取 `structured_response` + 抽取的 sources，构建含 `interpretation/sources/grounded=True` 的 `Quiz`；单测注入假 agent 验证字段填充与来源解析正确。
- [x] 5.2 实现优雅降级：缺 key / 关闭开关 / Agent 抛异常 / `structured_response` 为空时，回退现有 `build_quiz_chain`（v1），置 `grounded=False`、`sources=[]`、`interpretation=""`；`web_extract` 的 `failed_results` 不视为整体失败（可回退搜索摘要或 v1）；单测 mock agent 抛错与 extract 全失败，验证回退成功且不中断主流程。
- [x] 5.3 保留现有三级校验（题量/选项/答案一致性）与重试兜底，使其对接地与回退两条路径都生效；单测验证“校验失败→重试→最终兜底异常”路径。

## 6. 数据模型、持久化与历史详情

- [x] 6.1 在 `backend/app/models/quiz.py` 的 `Quiz` 增加 `interpretation: str=""`、`sources: list[Source]=[]`、`grounded: bool=False`，新增 `Source{title,url,score?,kind?}` 模型；`backend/app/models/user.py` 的 `QuizDetail` 增加同名字段；验证模型可序列化。
- [x] 6.2 新增 DB 迁移脚本：`ALTER TABLE quiz_sessions ADD COLUMN interpretation TEXT NULL / sources_json JSON NULL / grounded TINYINT(1) NOT NULL DEFAULT 0`（每列加中文 COMMENT），并同步更新 `sql/init_mysql.sql`；已在远端 MySQL 的 ai_learn 库执行迁移并 SHOW COLUMNS 验证通过、旧数据兼容（新列默认 NULL/0）。
- [x] 6.3 `backend/app/repositories/quiz_repository.py` 的 `insert_quiz_session` 增参；`persistence_service.persist_quiz` 落 interpretation/sources/grounded；`history_service.get_detail` 回填这些字段到 `QuizDetail`；用 db/mock 测试验证存取一致。

## 7. API 响应扩展

- [x] 7.1 `backend/app/api/v1/routes/quiz.py` 的 `/generate` 响应增加 `interpretation`、`sources`、`grounded`；历史详情响应同步带出；扩展 `test_quiz_api` 验证响应含新字段（覆盖接地态与降级态）。

## 8. 前端类型与展示

- [x] 8.1 `frontend/src/types/index.ts` 新增 `Source{title,url,score?,kind?}`，`Quiz` 与 `QuizDetail` 增 `interpretation?/sources?/grounded?`；验证 `npm run build:weapp` 类型检查通过。
- [x] 8.2 `frontend/src/pages/quiz/index.tsx` 展示 interpretation 标注与“参考来源”列表（标题 + 链接文本，可按 kind 区分“搜索/网页”，可选复制），未接地或来源为空时隐藏来源区；用微信开发者工具验证接地态与空态渲染。
- [x] 8.3 `frontend/src/pages/report/index.tsx` 回看模式在 `detail.sources` 存在时展示来源；验证回看页渲染。
- [x] 8.4 首页/闯关 loading 文案体现“检索/抓取 + 出题”；验证展示（纯文案，可选）。

## 9. 集成与回归验证

- [x] 9.1 端到端（关键词接地）：配置 `TAVILY_API_KEY` 启动后端，对多义/新主题（如 “Harness Engineering”）调 `/api/v1/quiz/generate`，验证 `grounded=true`、`interpretation` 标注合理领域、`sources` 非空且 URL 真实、题目贴合检索结果。
- [x] 9.2 端到端（网页抽取）：输入含一个真实网页 URL，验证 Agent 走 `web_extract` 抓取正文出题，`sources` 含该 URL，题目事实与页面一致；并验证抽取失败时回退到搜索或 v1。
- [x] 9.3 端到端（降级）：清空 key 或关闭 `QUIZ_GROUNDING_ENABLED`，验证走 v1、`grounded=false`、`sources=[]`，前端不展示来源区且答题/讲解正常。
- [x] 9.4 全量回归：`cd backend && pytest` 全绿 + `cd frontend && npm run build:weapp` 成功。

## Workflow follow-up

- 在项目评审要求满足后归档本 change（`openspec archive`）。
- 验证归档结果（`openspec show` 确认 `quiz-generation` capability 已并入主 specs）。
