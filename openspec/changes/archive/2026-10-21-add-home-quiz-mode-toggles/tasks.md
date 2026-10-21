# Tasks

## 1. 请求契约与校验（TDD）

- [x] 1.1 先写失败测试 `backend/tests/test_quiz_request_modes.py`：默认 `use_web_search=false` / `use_knowledge_base=false` / `document_id=null`；联网与知识库互斥；知识库缺文档被拒；非知识库携带文档被拒；旧字段 `document_ids` 被拒；验证：`cd backend && .venv/Scripts/python -m pytest tests/test_quiz_request_modes.py -q` 先红
- [x] 1.2 修改 `app/models/quiz.py`：删除 `document_ids`，新增三个字段与 Pydantic validator，并对任务创建请求启用 `extra="forbid"`；验证：1.1 测试转绿
- [x] 1.3 更新 `app/models/quiz_job.py` 与既有测试中所有请求字段 `document_ids` 调用点；`KnowledgeScope.document_ids` 作为内部检索范围保留；验证：请求层无 `document_ids` 残留，且 `cd backend && .venv/Scripts/python -m pytest -q` 通过（381 passed）

## 2. 任务创建、执行与路由

- [x] 2.1 先写失败测试：`create_job` 将三个来源参数写入 `params_json`；不再因存在 ready 文档自动启用知识库；知识库任务强制 `generate_images=false`；后台执行使用创建时保存的参数；验证：`cd backend && .venv/Scripts/python -m pytest tests/test_quiz_job_service.py tests/test_quiz_job_kb.py -q` 先红
- [x] 2.2 修改 `app/services/quiz_job_service.py`：`create_job` 落新参数；`_resolve_knowledge_scope` 只在 `use_knowledge_base=true` 时返回单文档 scope，并在执行开始时重新校验文档归属/就绪；验证：2.1 测试转绿
- [x] 2.3 先写失败测试：全关走未接地链；仅联网走接地链；知识库走单文档严格链；知识库无相关内容降级未接地且 `grounded=false`、来源为空；文档失效仍 failed；验证：`tests/test_quiz_service_modes.py`、`test_quiz_service_grounding.py`、`test_quiz_service_kb.py` 覆盖
- [x] 2.4 修改 `app/services/quiz_service.py`：按三个开关路由为三条互斥路径；移除 `_generate_home_quiz_with_knowledge` 混合路由与相关测试；`_generate_document_quiz` 在无有效知识库来源时降级 `_generate_plain`，文档失效仍抛可读错误；验证：2.3 测试转绿
- [x] 2.5 调整 `app/prompts/quiz_prompt.py` 与 `build_knowledge_base_tool` 的文档范围说明，将「文档一键闯关」改为「用户所选单份文档」，并更新 `tests/test_prompt_contract.py` / `tests/test_knowledge_base_tool.py`；验证：`cd backend && .venv/Scripts/python -m pytest tests/test_prompt_contract.py tests/test_knowledge_base_tool.py -q` 通过

## 3. Profile 能力标志

- [x] 3.1 先写失败测试 `backend/tests/test_quiz_capabilities.py`（可并入 `test_user_api.py`）：profile 返回 `quiz_capabilities`；联网/知识库/生图能力随配置变化；生图未就绪时 `image_quota.available=false`；验证：`cd backend && .venv/Scripts/python -m pytest tests/test_quiz_capabilities.py tests/test_user_api.py -q` 先红
- [x] 3.2 修改 `app/models/user.py` 与 `app/services/user_service.py`：新增 `QuizCapabilitiesOut` 与 `ProfileOut.quiz_capabilities`，按设置计算能力并修正 `image_quota.available`；验证：3.1 测试转绿

## 4. 首页三 chip 与知识库单选

- [x] 4.1 更新 `src/types/index.ts`：`QuizGenerateParams` 改为 `use_web_search` / `use_knowledge_base` / `document_id`，`UserProfile` 增加 `quiz_capabilities`；验证：`npm run build:weapp` 通过
- [x] 4.2 改造 `src/pages/index/index.tsx`：新增联网/今日配图/知识库三个 chip，默认全关；联网与知识库互斥；知识库选中时配图置灰；配图 chip 展示 `今日配图（used/limit）`；展示模式摘要；验证：构建通过，H5 浏览器实测全关/联网/配图/知识库组合与摘要均正确
- [x] 4.3 实现知识库单选面板：复用 `getKnowledgeOverview`，只列 `ready` 文档，单选替换，空态「去题库上传」并复用 TabBar 的 `reLaunch` 跳题库；选择文档且输入为空时预填基于文档的出题提示；验证：H5 浏览器实测单选替换、互斥、预填与摘要正确；空态跳转按同一 `reLaunch` 路径实现
- [x] 4.4 扩展 `ActiveJob` 保存 `use_web_search` / `use_knowledge_base` / `document_id` / `document_name`，`useDidShow` 恢复轮询时同步恢复 chip；验证：H5 写入含 KB 文档的 active job 后重进，chip、摘要、输入框与“出题中”状态均恢复
- [x] 4.5 补充 `src/pages/index/index.scss` 的 chip、选中态、禁用态与底部选择面板样式，小屏允许换行；验证：H5 375px 宽度实测三 chip 同排无溢出，chip 高度提升到 38 CSS px
- [x] 4.6 手工走查首页路径：全关、仅联网、仅知识库、切换互斥、配额满禁用、无 ready 文档空态、任务恢复；验证：H5 实测摘要与禁用态；真实任务 `params_json` 核对为全关/仅联网/仅知识库三种组合，`grounded` 与来源数符合预期；配额满通过 `IMAGE_DAILY_LIMIT=0` 实测 chip 禁用且点击无效

## 5. 题库页移除开始闯关

- [x] 5.1 修改 `src/pages/bank/index.tsx`：删除 `onStart`、任务创建、轮询、加载遮罩、`ACTIVE_JOB_KEY` 相关逻辑与 imports；保留上传、列表、状态、删除；文案改为「上传资料，在首页选择文档出题」；验证：`npm run build:weapp` 通过，`grep` 题库页无 `createQuizJob` / `onStart` / 加载遮罩残留
- [x] 5.2 清理 `src/pages/bank/index.scss` 中不再使用的加载遮罩/出题按钮样式（若确认无其他页面引用）；验证：构建通过，题库页无样式缺失
- [x] 5.3 手工验证题库页：上传、状态刷新、删除仍正常；页面无「开始闯关」，点击文档卡片不会创建任务；验证：上传临时 md 文档变为 ready 后删除成功，H5 题库页只展示删除按钮

## 6. 阶段耗时埋点

- [x] 6.1 先写失败测试 `backend/tests/test_quiz_job_timings.py`：成功任务包含 queue / validate_scope / generate / research / phase2 / images / persist / total 与调用计数；失败任务包含已发生阶段与 `error_stage`；全关路径 research / phase2 / images 为 0；知识库降级记录 `path` 与 `fallback_reason`；验证：`cd backend && .venv/Scripts/python -m pytest tests/test_quiz_job_timings.py -q` 先红后绿（8 passed）
- [x] 6.2 数据库：`sql/init_mysql.sql` 增加 `timings_json JSON NULL COMMENT '各阶段耗时与调用次数JSON（毫秒），用于定位慢点'`，新增 `sql/migrations/20261021_add_quiz_job_timings.sql`（information_schema 判重，可重复执行）；验证：迁移已由用户执行；`information_schema.COLUMNS` 确认列存在且为 `json / NULL`，注释正确
- [x] 6.3 `app/repositories/quiz_job_repository.py`：`mark_completed` / `mark_failed` 增加可选 `timings` 参数并写入 `timings_json`；补充仓储测试；验证：仓储测试通过，`timings=None` 时写入 NULL
- [x] 6.4 `app/services/quiz_job_service.py` 与 `app/services/quiz_service.py`：`create_job` 记录 `submitted_at`，`_run_job` 汇总 queue / validate_scope / generate / images / persist / total；`generate_quiz` 接受可选 `timings`，`_generate_grounded` 填充 research / phase2 / LLM 与工具调用次数 / 路径 / 降级原因；验证：6.1 测试转绿
- [x] 6.5 终端日志：任务终态输出一条 `quiz_job_timing`，字段与 `timings_json` 对齐；验证：单测 capture 成功/失败任务日志均包含 `quiz_job_timing`
- [x] 6.6 查询验证：用 design.md 中的 SQL 查最近任务，核对 `total_ms` 与 queue / validate_scope / generate / images / persist 之和接近（允许少量调度差值），并确认 `path` 与 `grounded` 正确；验证：8 条真实任务差值 45~341ms；`path` 覆盖 plain / web / knowledge_base / knowledge_base_fallback_plain，失败任务含 `error_stage=validate_scope`，与 `quiz_job_timing` 日志一致

## 7. 集成与回归

- [x] 7.1 跑后端全量测试：`cd backend && .venv/Scripts/python -m pytest -q`；验证：392 passed，覆盖默认全关、互斥、知识库降级、文档失效与阶段耗时
- [x] 7.2 端到端验证七条路径：全关最快出题、仅联网、仅知识库、知识库无内容降级、文档删除后失败、配图额度满、任务恢复；验证：全关 3.6s path=plain、联网 12.0s grounded + 8 来源、知识库 12.7s path=knowledge_base + 文档来源、无内容 10.6s path=knowledge_base_fallback_plain grounded=false 空来源、排队中删文档任务 failed（error_stage=validate_scope）、额度满 chip 禁用且点击无效、H5 重进恢复联网 chip/摘要/输入并继续轮询
- [x] 7.3 回归既有链路：历史记录、断点续答、报告生成、金币累加与来源展示行为不变；验证：真实任务走通历史列表/详情、进度上报 2/2 题、报告 accuracy=50 落库、答对 1 题金币 +10、联网历史详情 8 条来源且 grounded=true
- [x] 7.4 全局检索确认清理完成：请求字段 `document_ids`、`_generate_home_quiz_with_knowledge`、「开始闯关」无生产代码残留；`KnowledgeScope.document_ids` 作为内部检索范围保留；验证：`grep -rn` 已确认
- [x] 7.5 前端最终构建与浏览器验证：`npm run build:weapp` 与 `npm run build:h5` 均成功；H5 浏览器实测首页三 chip、互斥、预填、题库页无开始闯关；微信开发者工具导入由用户复核

## Workflow follow-up

- 评审通过后归档本 change，并同步 delta spec 到主 spec。
- 归档后复核 `openspec/specs/quiz-generation/spec.md` 与 `quiz-generation-jobs/spec.md` 已合并 REMOVED/MODIFIED 内容。
