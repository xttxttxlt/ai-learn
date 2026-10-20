# Design

## Context

- 出题链路的接地路径是两阶段同步调用：Tavily Agent 检索 → json_mode 结构化生成，加合重试后常超过 60s（见 proposal.md - Why）。
- 现有 `generate_quiz` 是同步阻塞函数，路由里用 `run_in_threadpool` 包裹；`persist_quiz` 依赖登录用户，落库失败只记日志、不影响主流程（`backend/app/services/persistence_service.py`）。
- 前端请求层统一 `Taro.request` + 60s 超时与 `{code,message,data}` 信封（`frontend/src/services/request.ts`）；首页已是静默登录 + loading 的交互结构（`frontend/src/pages/index/index.tsx`）。
- 数据库访问走 aiomysql 异步连接池（`backend/app/core/db.py`）；建表统一在 `sql/init_mysql.sql`（幂等）+ `sql/migrations/` 版本脚本。
- 约束：单实例部署、个人项目 MVP，不引入消息队列与多进程 worker。

## Goals / Non-Goals

**Goals:**

- 出题请求在 1s 内返回任务标识，生成在后台继续，结果可可靠取回。
- 任务幂等、归属明确、有终态兜底（超时 / 重启），前端可恢复轮询。
- 复用现有 `generate_quiz` 与持久化链路，生成内容契约不变。

**Non-Goals:**

- 报告生成异步化、任务列表 / 管理界面、多实例与任务分片、进度阶段细分（用户已拍板仅 running）。

## Decisions

### 1. 执行载体：进程内后台任务 + 现有线程池

创建接口内 `asyncio.create_task` 提交任务协程，协程内用 `run_in_threadpool` 执行现有同步 `generate_quiz`，并用 `asyncio.Semaphore(2)` 限制并发（配置项 `quiz_job_max_concurrency`）。任务未完成时进程重启会丢失，由启动清理兜底。

- 备选：Celery/RQ + Redis —— 引入 broker 与独立 worker，MVP 过重；`BackgroundTasks` —— 绑定响应周期、无并发控制与终态管理，放弃。

### 2. 任务存储：新增 `quiz_jobs` 表，结果落在任务行

任务行包含 `status`、`params_json`、`result_json`、`error_message` 与时间戳。完成后 `result_json` 存完整题库，查询接口直接读任务行交付；`quiz_sessions` 仍是历史 / 断点续答的权威副本。

- 备选：只存 `quiz_id` 查询时联表 —— 落库失败时无结果可交付（现有约束允许落库失败不影响用户拿到题库），放弃。

### 3. 接口形状：新增 `POST/GET /api/v1/quiz/jobs`，删除同步生成接口

- `POST /api/v1/quiz/jobs`：body = `user_input / question_count / difficulty / request_id`；同步做长度与敏感词校验；`get_current_user` 鉴权；返回 `{job_id, status}`。
- `GET /api/v1/quiz/jobs/{job_id}`：返回 `{job_id, status, quiz?, error?}`；查询强制 `user_id` 归属过滤，非归属返回未找到。
- 响应保持现有 `ok()` 信封与 HTTP 200 约定；删除 `POST /api/v1/quiz/generate` 路由。
- 备选：把原接口改造成返回 job_id —— 同名接口语义突变易混淆，弃。

### 4. 幂等：客户端 `request_id` + 数据库唯一键

前端每次「提交生成」生成一个新的 `request_id`（时间戳 + 随机串）；`uk_quiz_jobs_user_request (user_id, request_id)` 冲突时读取并返回既有任务。重试生成视为新意图，使用新的 `request_id`。

### 5. 状态机与兜底

`pending → running → completed | failed` 单向流转，`failed`/`completed` 写 `finished_at`。不细分 stage（用户拍板前端仅显示生成中）。

- 超时：查询接口惰性判定，`running` 且 `created_at` 超过 `quiz_job_timeout_seconds`（默认 300s）→ 置 failed。
- 重启清理：lifespan 启动时 `UPDATE quiz_jobs SET status='failed', ... WHERE status IN ('pending','running')`。
- 备选：独立定时清理任务 —— 需要调度器且收益低，弃。

### 6. 前端：首页承载 + 本地恢复

- 存储键 `ail_active_job`：`{job_id, user_input, question_count, created_at}`，创建成功即写入，到达终态清理。
- 轮询：前 5 次 3s（约 15s），之后 5s 一次；单次网络失败不判失败；总等待 6 分钟（后端 5 分钟兜底 + 缓冲）后按失败处理。
- 完成：`setCurrentQuiz(quiz)` → 跳答题页；失败：展示错误 + 恢复输入以便重试。
- 恢复：`useDidShow` 检查 `ail_active_job`，存在则续轮询（覆盖切后台、重进小程序、从其他页面返回）。
- 备选：独立「生成中」页面 —— 体验更聚焦但新增页面与路由，用户已拍板用首页承载。

### 7. 配置项

`backend/app/core/config.py` 新增：`quiz_job_timeout_seconds: int = 300`、`quiz_job_max_concurrency: int = 2`。

### 8. 数据库

`sql/init_mysql.sql` 追加 `quiz_jobs`（中文字段注释、utf8mb4、外键 `user_id → users.id` ON DELETE CASCADE），并新增 `sql/migrations/20261020_add_quiz_jobs.sql`：

- `job_id` 唯一；`uk_quiz_jobs_user_request (user_id, request_id)`；`idx_quiz_jobs_status_created (status, created_at)`。
- `params_json` 存出题参数；`result_json` 存完成题库；`error_message` 存可读错误摘要（截断存储）。

## Risks / Trade-offs

- [进程内任务随重启丢失（含开发期 --reload）] → 启动清理置 failed + 前端失败可重试；单实例假设写入非目标。
- [出题现在强依赖 MySQL 可用（此前匿名可出题不依赖落库）] → 连接池不可用时创建接口明确返回服务不可用，不静默降级。
- [并发上限 2 导致高峰排队，任务停留 running] → 5 分钟超时兜底 + 前端总等待上限，失败后用户可重试。
- [轮询对 DB 的压力] → 前 5 次 3s、之后 5s 退避；同一用户同时仅允许一个活动任务在轮询。
- [前后端接口不兼容，需同时发布] → 个人项目接受短窗口不可用；回滚方案为恢复同步路由代码（quiz_jobs 表可保留）。
- [重复点击产生双任务] → 幂等唯一键 + 前端按钮禁用双保险。

## Migration Plan

1. 执行 `sql/migrations/20261020_add_quiz_jobs.sql`（或依赖启动自动建表），确认 `quiz_jobs` 存在。
2. 后端部署：新增 jobs 路由与服务、删除同步路由；确认启动清理生效。
3. 前端发布：切换创建 + 轮询流程，清理旧 loading 逻辑。
4. 回滚：后端恢复 `POST /quiz/generate`（旧代码）并让前端回退；`quiz_jobs` 表保留不删，避免删表风险。

## Open Questions

- 已完成 / 失败任务的保留时长与清理策略（是否需要定期删除历史任务行）—— 可后续单独处理，不影响本次实现。