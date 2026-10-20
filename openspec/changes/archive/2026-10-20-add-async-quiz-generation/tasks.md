# Tasks

## 1. 数据层与配置

- [x] 1.1 `sql/init_mysql.sql` 追加 `quiz_jobs` 建表（job_id 唯一键、`uk_quiz_jobs_user_request (user_id, request_id)`、`idx_quiz_jobs_status_created (status, created_at)`、外键 user_id → users.id、中文字段注释）；验证：本地执行后 `SHOW CREATE TABLE quiz_jobs` 包含全部键、外键与注释
- [x] 1.2 新增 `sql/migrations/20261020_add_quiz_jobs.sql`（IF NOT EXISTS，与 init 脚本内容一致）；验证：本地 MySQL 连续执行两次均无报错
- [x] 1.3 `backend/app/core/config.py` 增加 `quiz_job_timeout_seconds: int = 300` 与 `quiz_job_max_concurrency: int = 2`；验证：读取 `get_settings()` 输出两个新字段，现有测试全绿

## 2. 后端任务模型与仓储

- [x] 2.1 新增 `app/models/quiz_job.py`：任务状态（pending/running/completed/failed）、创建请求（user_input / question_count / difficulty / request_id）、查询响应（job_id / status / quiz / error）模型；验证：新增单测覆盖 request_id 缺失、题量越界、状态枚举取值
- [x] 2.2 新增 `app/repositories/quiz_job_repository.py`：创建（唯一键冲突后回读既有任务实现幂等）、按 job_id + user_id 查询、置 running / completed / failed、惰性超时置 failed（条件更新）、启动清理（pending/running → failed）；验证：用 `tests/fake_db.FakeDB` 写仓储单测，断言 SQL 参数包含 user_id 归属过滤、幂等回读分支、条件更新的 WHERE 状态集合

## 3. 任务服务与路由

- [x] 3.1 新增 `app/services/quiz_job_service.py`：创建（清洗与敏感词校验 → 落 pending → 提交后台协程）、执行器（信号量限并发 → running → `run_in_threadpool(generate_quiz)` → `persist_quiz` → completed，异常 → failed 截断错误）、查询（惰性超时判定 + 归属校验）；验证：新增 `tests/test_quiz_job_service.py` monkeypatch `generate_quiz` / `persist_quiz`，断言各状态流转、result_json 写入、落库失败仍 completed
- [x] 3.2 路由改造 `app/api/v1/routes/quiz.py`：新增 `POST /api/v1/quiz/jobs`（`get_current_user`）与 `GET /api/v1/quiz/jobs/{job_id}`，删除同步 `POST /quiz/generate`；`app/main.py` lifespan 增加启动清理调用；验证：新增 `tests/test_quiz_jobs_api.py` 覆盖创建成功、参数校验错误、未登录、幂等返回同一 job_id、查询 pending/running/completed/failed、越权与不存在均返回未找到
- [x] 3.3 更新受影响的既有测试（`tests/test_quiz_api.py` 中同步接口用例迁移或删除）；验证：`pytest backend/tests -q` 全绿，且存在一条断言旧路径 `/api/v1/quiz/generate` 返回 404 的用例

## 4. 前端改造

- [x] 4.1 `src/types/index.ts` 与 `src/services/api.ts`：新增任务类型与 `createQuizJob` / `getQuizJob`；验证：`npm run build:weapp` 一次性构建通过
- [x] 4.2 `src/pages/index/index.tsx`：生成流程改为 ensureLogin → 生成 request_id → 创建任务 → 写 `ail_active_job` → 轮询（前 5 次 3s、之后 5s、单次失败继续重试、总等待 6 分钟）→ completed 后 `setCurrentQuiz` 跳答题页 / failed 展示错误并恢复输入；`useDidShow` 检测 `ail_active_job` 恢复轮询；终态清理存储；验证：微信开发者工具手工走通正常生成、断网轮询恢复、切后台重进恢复、后端置 failed 时提示重试四条路径
- [x] 4.3 清理旧同步生成调用（移除 `generateQuiz` API 与旧 loading 逻辑）；验证：全局搜索无 `generateQuiz(` 调用残留，构建通过

## 5. 集成验证

- [x] 5.1 端到端跑通联网接地出题完整链路（创建 → running → completed → 答题 → 报告），确认历史记录、断点续答、金币累加行为与改造前一致；验证：本地起后端 + 开发者工具实测并核对后端日志中任务状态流转
- [x] 5.2 异常路径实测：服务重启后残留 running 任务被置 failed、把任务置为超时状态后查询返回 failed、用他人凭证查询任务返回未找到；验证：本地实测记录 + 对应单测通过

## Workflow follow-up

- 评审通过后归档本 change，并同步 delta spec 到主 spec。