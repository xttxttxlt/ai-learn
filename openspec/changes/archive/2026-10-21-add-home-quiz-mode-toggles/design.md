# Design

## Context

动机与范围见 `proposal.md`，行为契约见 `specs/quiz-generation/spec.md` 与 `specs/quiz-generation-jobs/spec.md`。当前实现约束：

- 请求模型 `QuizGenerateRequest` 使用 `document_ids: list[str]` 表示文档范围，`generate_images` 表示是否配图；`QuizJobCreateRequest` 直接继承它。
- 创建任务时，`_resolve_knowledge_scope` 只要查到用户有任意已就绪文档，就自动返回全库 `KnowledgeScope`；没有请求级开关。
- `_grounding_enabled(settings)` 只看全局 `enable_web_search` 与 `tavily_api_key`；未指定文档时会自动走联网接地。
- 路由：文档范围走 `_generate_document_quiz`（仅知识库、失败即报错）；首页有知识库范围走 `_generate_home_quiz_with_knowledge`（知识库 + 联网混合）；无范围且联网开启走仅联网 Agent。
- `quiz_jobs.params_json` 已能持久化任意请求参数，本次无需改表。
- 前端首页已有配图开关、任务轮询与 `ail_active_job` 恢复；题库页有「开始闯关」、轮询与加载遮罩。
- `GET /api/v1/user/profile` 已返回 `image_quota`，但未返回联网/知识库/生图能力是否就绪；`image_quota.available` 目前只反映额度读取是否成功。
- `quiz_jobs` 已有 `params_json` / `result_json` / `created_at` / `finished_at`，但没有阶段耗时字段；现有日志只有零散事件，无法直接回答“哪一段慢”。
- 后端单进程异步任务、TDD、增量兼容；不新增依赖。

## Goals / Non-Goals

**Goals:**

- 首页三个 chip 显式控制来源，默认全关时只做一次结构化生成。
- 知识库只能从题库 Tab 的已就绪文档中单选一份，且与联网互斥。
- 知识库严格模式无相关内容时降级通用，文档失效仍明确失败。
- 题库页只保留上传与管理，不再发起出题。
- 请求参数可校验、可持久化，任务恢复时前端状态一致。
- 记录每个任务各阶段耗时与调用次数，支持日志和 SQL 查询慢点。

**Non-Goals:**

- 联网 + 知识库混合检索、多选文档、首页上传。
- 配图异步化、研究 Agent 收紧、题量调整。
- 跨会话记忆 chip 选择、题库页跳转首页。
- 修改题目结构、历史、报告、金币与断点续答链路。
- 完整 APM/链路追踪、LLM token/成本统计、实时监控面板与告警。

## Decisions

### 决策 1：请求契约改为三个显式字段

**选择：**

- `QuizGenerateRequest` 删除 `document_ids`，新增：
  - `use_web_search: bool = False`
  - `use_knowledge_base: bool = False`
  - `document_id: Optional[str] = None`
- 用 Pydantic validator 统一校验：
  - 两个开关同时为 true → 校验错误。
  - `use_knowledge_base=true` 且 `document_id` 为空 → 校验错误。
  - `use_knowledge_base=false` 且携带 `document_id` → 校验错误。
- 创建任务时把三个字段写入 `params_json`；后台执行使用创建时保存的值，不重新读取全局默认。
- 任务创建请求启用 `extra="forbid"`，旧客户端若仍发送 `document_ids` 会直接收到 422，避免「选了文档却生成通用题」的静默降级。

**理由：** 产品规则是单选，单个 `document_id` 比 `list[str]` 更难误用；请求级开关让默认全关真正生效。**BREAKING** 通过前后端同版本发布消化。

**备选：** 保留 `document_ids` 并限制长度为 1。字段语义仍像多选，且容易在旧数据/测试中混入多值，不采用。

### 决策 2：路由简化为三条互斥路径

**选择：** `generate_quiz` 只保留三条路径：

1. `use_knowledge_base=true` → `_generate_document_quiz`（仅所选文档、不联网）。
2. 否则 `use_web_search=true` 且全局联网能力可用 → 仅联网研究 Agent。
3. 否则 → 未接地链。

配套调整：

- `_resolve_knowledge_scope` 只在 `use_knowledge_base=true` 时返回 `KnowledgeScope(user_id, [document_id])`，不再查询 `count_ready`。
- 联网判断改为 `request.use_web_search and settings.enable_web_search and bool(settings.tavily_api_key)`。
- 删除 `_generate_home_quiz_with_knowledge` 的混合路由；该函数不再被首页调用，连同仅服务于它的测试一起清理。

**理由：** 联网与知识库互斥后，混合路由不可达；保留它会让分支和失败语义变复杂。三条路径与产品矩阵一一对应，便于测试。

**备选：** 保留混合路由，仅用开关控制。不可达代码会长期存在，不采用。

### 决策 3：知识库严格模式“无内容降级通用”

**选择：**

- 创建任务时沿用 `validate_document_scope` 校验文档归属与就绪状态；任务开始执行时再查一次文档状态，失效/越权/未就绪直接失败，提示「文档不可用，请重新上传」。
- 文档有效但研究阶段没有产出有效知识库来源（无检索结果、模型未引用分块、接地链失败）时：
  - 记录 `knowledge_quiz_fallback_plain` 日志；
  - 调用未接地链生成题库；
  - 返回 `grounded=false`、`sources=[]`，任务仍为 `completed`。
- 运行中文档被删除的极端竞态按「无内容」处理；创建与执行开始的两次校验覆盖绝大多数失效场景。

**理由：** 用户已拍板“文档没覆盖就降级通用”，避免选了一份不相关文档就直接失败；同时保留文档已失效时的明确失败，避免用户误以为题目来自文档。

**备选：** 所有知识库失败都降级通用。会让已删除文档也静默产出通用题，不采用。

### 决策 4：能力标志随 profile 下发

**选择：**

- `ProfileOut` 增加 `quiz_capabilities`：
  - `web_search`：`enable_web_search and tavily_api_key`
  - `knowledge_base`：`settings.knowledge_base_ready`
  - `image_generation`：`settings.image_generation_ready`
- 同时修正 `image_quota.available`：生图能力未就绪时也为 false，而不只是额度读取失败时。
- 前端用这些标志决定 chip 是否展示/可点；后端对不可用能力的开启请求仍按未接地链回退并记录日志。

**理由：** 首页本来就请求 profile，复用它不增加一次网络往返；避免“开关能点、后端没 key”的假开关。

**备选：** 新增 `/api/v1/quiz/options`。多一次请求，收益一样，不采用。

### 决策 5：首页 chip 与知识库单选交互

**选择：**

- 状态：`useWeb`、`useImages`、`useKb`、`selectedDoc`；默认全部关闭。
- 互斥：开启联网时清空 `selectedDoc` 并关闭知识库；选择文档时自动关闭联网。
- 知识库选中时 `useImages=false`，配图 chip 置灰。
- 配图 chip 文案为 `今日配图（used/limit）`；额度满或能力不可用时置灰。
- 知识库面板复用 `GET /api/v1/knowledge-base`，只展示 `status=ready`，单选；空态提供「去题库上传」，复用现有 TabBar 的 `reLaunch` 方式跳到题库 Tab（项目未配置原生 tabBar）。
- 选择文档且输入为空时，预填「请根据文档《文档名》生成闯关题目，覆盖核心知识点」，保留原题库一键闯关的顺手体验。
- 摘要行映射：
  - 全关：`本次：通用出题（最快）`
  - 联网：`本次：联网检索`
  - 知识库：`本次：基于《文档名》出题`
- `ActiveJob` 增加 `use_web_search`、`use_knowledge_base`、`document_id`、`document_name`；`useDidShow` 恢复轮询时同步恢复 chip 状态。
- 题库页删除 `onStart`、轮询、加载遮罩与相关 imports/styles；保留上传、列表、状态、删除；文案改为「上传资料，在首页选择文档出题」。

**理由：** 与用户给的 DeepSeek chip 交互一致，且把“本次为什么慢”显式化；知识库单选和空态跳转不引入新上传入口。

**备选：** 保留原有配图大开关，只新增两个开关。视觉与交互不统一，不采用。

### 决策 6：阶段耗时埋点

**选择：**

- 使用 `time.perf_counter()` 单调时钟计算耗时，不用 `created_at` / `NOW()` 或墙钟差，避免 MySQL 时区与系统时钟回拨影响。
- `create_job` 记录 `submitted_at`；任务拿到信号量后记录 `run_started_at`，得到 `queue_ms`。`_run_job` 汇总 `validate_scope_ms`、`generate_ms`、`images_ms`、`persist_ms`、`total_ms`。
- 给 `generate_quiz` 增加可选 `timings: Optional[dict]` 参数；`_generate_grounded` 填充 `research_ms`、`phase2_ms`、`research_llm_calls`、`research_tool_calls`、`phase2_attempts`、`path`、`fallback_reason`。不改变返回值和现有调用契约，测试可注入空 dict 断言键值。
- 记录字段：
  - 耗时：`queue_ms` / `validate_scope_ms` / `generate_ms` / `research_ms` / `phase2_ms` / `images_ms` / `persist_ms` / `total_ms`
  - 上下文：`path`（`plain` / `web` / `knowledge_base` / `knowledge_base_fallback_plain`）、`research_llm_calls`、`research_tool_calls`、`phase2_attempts`、`question_count`、`source_count`、`grounded`、`error_stage`
- 持久化：`quiz_jobs` 新增 `timings_json JSON NULL COMMENT '各阶段耗时与调用次数JSON（毫秒），用于定位慢点'`；`mark_completed` / `mark_failed` 增加可选 `timings` 参数写入。同步更新 `sql/init_mysql.sql` 与新增 additive migration。
- 日志：任务终态统一输出一条 `quiz_job_timing`，字段与 JSON 对齐，并带 `job_id`、`user_id`、`status`；失败时同样输出已发生阶段。
- 查询示例：

```sql
SELECT job_id, status, created_at,
       JSON_EXTRACT(timings_json, '$.total_ms') AS total_ms,
       JSON_EXTRACT(timings_json, '$.queue_ms') AS queue_ms,
       JSON_EXTRACT(timings_json, '$.research_ms') AS research_ms,
       JSON_EXTRACT(timings_json, '$.phase2_ms') AS phase2_ms,
       JSON_EXTRACT(timings_json, '$.images_ms') AS images_ms,
       JSON_UNQUOTE(JSON_EXTRACT(timings_json, '$.path')) AS path
FROM quiz_jobs
ORDER BY created_at DESC
LIMIT 50;
```

**理由：** 现有日志只能看事件顺序，无法量化“排队 / 研究 / 阶段二 / 配图”各占多少；JSON 列是 additive 变更，不改变既有查询，日志又能直接按任务筛选。

**备选：** 只写日志（无法 SQL 聚合）；单独建 metrics 表（当前规模过重）；接入 OpenTelemetry/Prometheus（单实例 MVP 过重）。

### 决策 7：测试与验证顺序（TDD）

**选择：**

- 先写失败测试：
  - 请求模型：默认值、互斥、知识库缺文档、非知识库带文档、旧字段被拒绝。
  - 任务服务：参数落库、不再自动启用知识库、联网开关透传。
  - 路由：全关走未接地；联网走接地；知识库走文档严格模式。
  - 降级：知识库无内容 → `completed` 且 `grounded=false`、来源为空；文档失效 → `failed`。
  - 配图：`use_knowledge_base=true` 时 `generate_images` 被忽略。
  - Profile：能力标志随配置变化；生图未就绪时 `image_quota.available=false`。
- 再实现后端，最后改前端；前端以 `npm run build:weapp` + 微信开发者工具手工验证。
- 回归现有 `pytest backend/tests -q`，重点覆盖原 `document_ids` 与自动知识库相关用例。

## Risks / Trade-offs

- [移除 `document_ids` 破坏旧客户端] → 前后端同版本发布；`extra="forbid"` 让旧请求显式失败；服务重启会把残留任务置 failed，无孤立数据。
- [知识库降级通用可能让用户误以为题目来自文档] → 返回 `grounded=false`、来源为空；后续可在答题页增加“未命中文档内容”提示（本期不做）。
- [能力标志过期] → 只用于 UI 展示，后端仍做回退；标志不参与任务执行正确性。
- [运行中文档被删除的竞态] → 创建与执行开始两次校验；极端竞态按无内容降级。
- [联网 + 知识库无法同时使用] → 产品已拍板互斥；用户可拆成两次任务。
- [三个 chip 在小屏拥挤] → chip 支持换行，知识库 chip 只显示截断文档名/已选状态，完整信息在选择面板中。
- [提示词仍带“文档一键闯关”措辞] → 仅知识库工具会被装配，提示与工具描述需改成“所选文档”，避免模型误判还有联网工具。
- [`timings_json` 膨胀] → 只存阶段汇总与计数，单条控制在 1KB 内，不存完整消息或工具正文。
- [加列影响现有查询/部署] → 使用可空列与 additive migration，先执行迁移再发后端；现有 `SELECT *` 与状态流转不受影响。
- [计时本身增加开销] → `perf_counter` 与少量计数为微秒级，不引入额外网络或 DB 调用。
- [失败任务缺少耗时] → `mark_failed` 同样写入已发生阶段；超时/重启清理暂不补 `timings_json`，仍可通过 `created_at` / `finished_at` 观察。

## Migration Plan

1. 数据库：在 `sql/init_mysql.sql` 与新增 `sql/migrations/20261021_add_quiz_job_timings.sql` 中加入可空 `timings_json JSON`（中文注释），先执行迁移。
2. 后端：改请求模型、任务服务、路由、仓储与埋点，先跑测试；再改前端首页与题库页。
3. 前后端同版本发布；发布说明注明旧版客户端创建任务会失败，需更新小程序。
4. 回滚：前后端一起回滚；`timings_json` 为可空附加列，保留不影响旧代码，确需清理再单独删列。
5. 发布后验证：全关、联网、知识库、知识库无内容降级、文档删除失败、配图额度满、任务恢复七条路径，并核对 `timings_json` 与 `quiz_job_timing` 日志字段。

## Open Questions

- 知识库降级通用时，答题页是否要显式提示“未命中文档内容，已按通用知识出题”？本期先只保证 `grounded=false` 与来源为空，后续可单独加提示。
- 后续是否要做管理端耗时看板或慢任务告警？本期只提供结构化日志与 SQL 查询。
