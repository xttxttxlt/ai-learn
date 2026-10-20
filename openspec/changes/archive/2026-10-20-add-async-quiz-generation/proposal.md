# Proposal

## Why

联网接地的两阶段出题（Tavily 检索 + 结构化生成）经常超过微信小程序单请求 60s 上限。当前同步 `POST /api/v1/quiz/generate` 会在请求被掐断时让用户只看到网络错误，而服务端的生成结果无人接收。异步任务 + 轮询让创建请求立即返回，生成在后台继续，结果可被可靠取回。

## What Changes

- 新增异步出题任务接口：`POST /api/v1/quiz/jobs` 立即返回 `job_id`，`GET /api/v1/quiz/jobs/{job_id}` 查询状态与结果。
- 新增 `quiz_jobs` 表与任务生命周期（`pending` / `running` / `completed` / `failed`），用客户端 `request_id` 做幂等去重。
- **BREAKING** 移除同步 `POST /api/v1/quiz/generate`，小程序前端改走新接口；旧版本客户端调用会得到 404。
- 创建任务要求已登录（沿用现有静默登录，不新增用户操作）；任务归属用户，完成后仍按原逻辑落 `quiz_sessions`。
- 任务超时兜底：`running` 超过 5 分钟置为 `failed`；服务启动时将残留的 `pending` / `running` 任务置为 `failed`。
- 前端在首页承载「生成中」状态：轮询前 5 次 3s（约 15s）后放宽到 5s，`job_id` 写入本地存储，退出首页或小程序重进后可恢复轮询。
- 不做：报告生成异步化、WebSocket/SSE、任务列表页、Celery/Redis、多实例部署。

## Capabilities

### New Capabilities

- `quiz-generation-jobs`: 异步出题任务的创建与幂等、后台执行与状态流转、状态查询与结果交付、超时与重启兜底。

### Modified Capabilities

- `quiz-generation`: 出题入口由同步调用改为异步任务且要求登录；前端改为轮询并可恢复；移除同步生成接口。题目结构、联网接地与降级等生成内容契约保持不变。

## Impact

- 后端：`app/api/v1/routes/quiz.py`（改造），新增任务路由/服务/仓储；`app/models/` 增加任务模型；`app/main.py` 增加启动清理；`sql/init_mysql.sql` 增加 `quiz_jobs` 建表，并提供 migration。
- 前端：`src/services/api.ts`、`src/pages/index/index.tsx`、`src/types/index.ts` 与本地存储键。
- 数据库：新增 `quiz_jobs` 表；`quiz_sessions` / `answer_records` / `reports` 结构不变。
- 依赖：不新增运行时依赖，使用 FastAPI 进程内后台任务执行现有 `generate_quiz`。
- 发布：前后端需一起上线；旧版小程序无法继续生成题目（仅影响生成入口，历史与报告接口不受影响）。
