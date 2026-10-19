# Proposal

## Why

大模型训练数据存在时间截点。当前出题链路（`backend/app/llm/quiz_chain.py`）只把用户原始文本直接喂给 DeepSeek flash，且出题 Prompt（`backend/app/prompts/quiz_prompt.py`）还鼓励“基于常识合理补充”，对新、冷门或多义主题会产生两类错误：一是编造过时/错误事实，二是选错领域。典型例子：用户输入 “Harness Engineering”，模型无法确定指 CI/CD 平台 Harness、电气线束工程、还是测试脚手架，从而给出另一个领域的题目与讲解。需要在出题前用联网检索到的权威、最新知识为出题“接地”（grounding），并把 AI 对多义主题的解读显式呈现给用户。此外，用户输入的可能不只是一句话，还可能是一个网页链接，因此接地既要能按关键词联网搜索，也要能直接抓取指定网址的正文内容。

## What Changes

- 出题新增“接地”路径：引入 LangChain Agent（`create_agent`），挂载官方 `langchain-tavily` 提供的搜索与抽取工具，出题前先联网获取最新权威信息，再基于获取到的事实生成题目，禁止凭空编造。
- 双接地来源：① 关键词联网搜索（`TavilySearch`）；② 抓取指定网址的整页正文（`TavilyExtract`）。当用户输入是/包含网页链接时，直接抽取该页面内容作为接地依据。
- 多实例工具策略：把上述工具注册成多个具名实例——“摘要检索”与“全文检索”（差异在 `include_raw_content` / `max_results` / `search_depth`）加“网页抽取”——一并交给 Agent，由模型自主决定何时调用哪个工具，并动态选择调用时可改的参数（`search_depth`、`time_range`、`include_domains` / `exclude_domains` 等），以兼顾国内外用户与不同复杂度的主题。
- 多义主题自动判定：Agent 依据检索结果锁定单一最相关领域/解读，并在题库中显式标注（interpretation），让用户一眼发现是否跑偏。
- 出题输出扩展：新增 `interpretation`（本次解读/领域标注）与 `sources`（参考来源标题 + URL，取自真实检索或网页抽取结果，去重、不可由模型编造）；新增 `grounded` 标记本次是否成功联网接地。
- 出题响应、落库与历史详情接口透出 `interpretation` / `sources` / `grounded`；前端闯关页与历史回看页展示“参考来源”（“本次解读”由后端 Agent 自行判定并保存，用于聚焦出题领域，不在前端展示）。
- 优雅降级：未配置 `TAVILY_API_KEY`、关闭接地开关、或搜索/Agent 失败时，自动回退到现有“未接地”出题链（`grounded=false`、`sources` 为空、`interpretation` 为空），绝不中断出题主流程，保留原有五级兜底与校验。
- 出题 Prompt 升级为 v2（接地版）：说明可用的检索/抽取工具与适用场景，引导模型先判断输入类型与主题复杂度，再自主选择工具与参数并基于获取到的事实出题；与现有 v1 并存以支持回退与对比。

## Capabilities

### New Capabilities
- `quiz-generation`: 把用户输入转换为结构化、可讲解、可复盘的闯关题库的能力。涵盖出题输入清洗与敏感词校验、（可选）联网检索接地、多义主题自动判定与解读标注、结构化题目输出与多级校验、参考来源透出、失败重试，以及未接地/检索失败时的优雅降级。

### Modified Capabilities
<!-- 项目当前 openspec/specs 为空，无既有 capability 的需求被修改。 -->

## Impact

- 后端代码：`app/llm/`（新增出题 Agent 与检索/抽取工具封装：`TavilySearch` 摘要实例 + 全文实例 + `TavilyExtract` 实例）、`app/prompts/quiz_prompt.py`（v2）、`app/llm/output_schemas.py`（`QuizOutputSchema` 增 `interpretation`）、`app/models/quiz.py`（`Quiz` 增 `interpretation`/`sources`/`grounded`，新增 `Source` 模型）、`app/services/quiz_service.py`（生成主流程改造）、`app/api/v1/routes/quiz.py`（响应增字段）、`app/core/config.py`（Tavily 搜索/抽取与接地配置）。
- 后端持久化：`app/services/persistence_service.py`、`app/repositories/quiz_repository.py`、`app/services/history_service.py`、`app/models/user.py`（`QuizDetail`）。
- 数据库：`quiz_sessions` 增 `interpretation` / `sources_json` / `grounded` 列；更新 `sql/init_mysql.sql` 并新增迁移脚本。
- 前端（Taro）：`src/types/index.ts`（`Quiz`/`QuizDetail`/新增 `Source`）、`src/pages/quiz/index.tsx`（展示参考来源）、`src/pages/report/index.tsx`（回看模式展示来源）。
- 依赖与环境：`langchain` 升级至 `>=1.0`（`create_agent`），新增 `langchain-tavily`、`tavily-python`；新增环境变量 `TAVILY_API_KEY` 及接地相关配置。
- 外部服务：Tavily 搜索 API（海外服务，本机直连可能需走代理 `127.0.0.1:7897`）。
- 不在本次范围：PDF/Word/视频等文档解析（网页 URL 正文抽取已在本次范围内）、私有知识库 RAG、以及“交互式歧义澄清”（本次采用自动判定 + 标注，不增加前后端往返）。
