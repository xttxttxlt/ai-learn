# Proposal

## Why

首页出题目前是隐式自动决策：只要用户有任意一份已就绪文档，后端就自动挂载知识库；联网又只由全局开关决定。用户无法控制本次是否检索、用哪份文档，简单问题也可能走多轮研究 Agent，耗时到分钟级。题库页的「开始闯关」又与首页出题形成两套入口、两套体验。

## What Changes

- 首页新增三个 chip：**联网检索**、**今日配图（3/100）**、**知识库**；默认全部关闭，全关时走一次结构化生成的未接地链。
- **知识库 chip** 打开底部选择器，只列题库 Tab 中已就绪文档，**单选一份**；选择器不提供上传，空态引导去题库 Tab。
- **联网与知识库互斥**：开启一个会自动关闭另一个，不允许同时生效。
- **知识库选中时配图置灰**：配图 chip 禁用并强制关闭，与「文档出题不配图」的现有约束一致。
- 后端请求显式化：新增 `use_web_search`、`use_knowledge_base` 与单个 `document_id`；只有知识库开关为真才解析文档范围，不再「有 ready 文档就自动启用」。
- 知识库严格模式（选文档、不联网）下，文档无相关内容时**降级为通用出题**，返回 `grounded=false`、`sources=[]`，不再直接失败。
- 题库页移除「开始闯关」按钮、轮询与 loading，只保留上传、文档列表、状态与删除；**不保留**「去首页出题」入口。
- **耗时埋点**：为每个任务记录排队、文档范围解析、研究、阶段二、配图、落库与总耗时，以及研究 LLM/工具调用次数、阶段二尝试次数、最终路径与降级原因；写入结构化日志与 `quiz_jobs.timings_json`，便于后续查询慢点。
- **BREAKING** 出题任务请求契约由 `document_ids: list[str]` 改为单个 `document_id: str | null`，并新增两个布尔开关；仅影响当前小程序客户端。
- 不做：多选文档、首页上传、联网 + 知识库混合、配图异步化、研究 Agent 收紧、跨会话记忆开关、题库页跳转首页、完整 APM/链路追踪与前端耗时看板。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `quiz-generation`: 首页出题由「自动接地」改为「用户显式选择模式」；新增三 chip 与知识库单选交互；移除题库页「开始闯关」；知识库严格模式无相关内容时降级为通用出题。
- `quiz-generation-jobs`: 任务创建参数改为显式 `use_web_search` / `use_knowledge_base` / 单个 `document_id`；文档范围只在知识库开关开启时生效；联网与知识库互斥；知识库任务强制不配图。

## Impact

- 后端：`app/models/quiz.py`、`app/models/quiz_job.py`（请求字段）、`app/services/quiz_job_service.py`（不再自动启用知识库、参数透传）、`app/services/quiz_service.py`（按开关路由、知识库严格模式降级）、`app/prompts/quiz_prompt.py`（单选文档范围下的工具说明）、`app/api/v1/routes/user.py` 或新增配置接口（下发联网/知识库/配图可用性）。
- 前端：`src/pages/index/index.tsx`（三 chip、知识库单选面板、模式摘要、active job 参数持久化）、`src/pages/bank/index.tsx`（移除开始闯关与轮询）、`src/types/index.ts`、`src/services/api.ts` 与相关样式。
- 测试：后端新增/调整请求校验与路由单测、知识库降级单测、阶段耗时单测；前端构建与微信开发者工具手工验证。
- 数据库：`quiz_jobs` 新增可空 `timings_json JSON` 列（中文注释），并提供 additive migration；开关与 `document_id` 继续存 `quiz_jobs.params_json`。
- 日志：新增 `quiz_job_timing` 结构化日志，字段与 `timings_json` 对齐，可按 `job_id` 或慢任务筛选。
- 依赖与部署：不新增依赖；前后端需一起上线，数据库迁移先行。
