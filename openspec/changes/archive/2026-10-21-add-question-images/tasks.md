# Tasks

## 1. 数据模型、配置与用量表

- [x] 1.1 先补测试再实现：`Question` 增加可选 `image_url`（默认 `None`），`QuizGenerateRequest` 增加 `generate_images`（默认 `False`）；测试旧题库 JSON 反序列化、无图题目序列化、新字段透传均通过（`pytest -q tests/` 对应用例）
- [x] 1.2 先补测试再实现：`Settings` 增加 `ENABLE_IMAGE_GENERATION`、`IMAGE_BASE_URL`、`IMAGE_MODEL`、`IMAGE_SIZE`、`IMAGE_TIMEOUT_SECONDS`、`IMAGE_MAX_CONCURRENCY`、`IMAGE_DAILY_LIMIT`、`COS_SECRET_ID/KEY/REGION/BUCKET/PUBLIC_BASE_URL/KEY_PREFIX`，并实现 `image_generation_ready`；测试配置齐全/缺项两种判断（`pytest -q tests/test_image_generation_config.py`）
- [x] 1.3 在 `sql/init_mysql.sql` 新增 `image_generation_usage` 表（每个字段中文 COMMENT、表级注释、`user_id` 外键、唯一键 `(user_id, usage_date)`），并新增 `sql/migrations/20261021_add_image_generation.sql`（纯新增、可重复执行、附回滚语句）；用测试或本地 MySQL 执行验证建表成功且可重复执行
- [x] 1.4 先补测试再实现：新增 `app/repositories/image_usage_repository.py`，提供当日用量查询、正数预留与失败退还（退还 SQL 使用 `GREATEST(0, ...)`）；用 FakeDB 断言 SQL 与参数（`pytest -q tests/test_image_usage_repository.py`）
- [x] 1.5 更新 `backend/requirements.txt` 增加 `cos-python-sdk-v5`，并同步 `backend/.env.example`、`backend/.env` 的 `IMAGE_*`、`COS_*` 空值/占位配置；确认 `.env` 仍被 gitignore，`.env.example` 可提交

## 2. 生图、转存与编排服务

- [x] 2.1 先补测试再实现：`build_image_prompt(question)` 依据知识点/题干/正确答案构建中文 Prompt，包含“不出现文字、字母、数字、水印”，并对长文本截断；测试单词题、长题干、无正确答案文本三种输入（`pytest -q tests/test_image_generation_service.py`）
- [x] 2.2 先补测试再实现：百炼同步生图客户端（`httpx`）按 `POST {IMAGE_BASE_URL}/services/aigc/multimodal-generation/generation` 发送 model/input/parameters，解析 `output.choices[0].message.content[*].image` 并下载图片字节；测试成功、HTTP 非 200、响应无图片、网络异常四种路径均返回可预期结果且不外抛
- [x] 2.3 先补测试再实现：COS 上传服务用 `CosConfig` + `CosS3Client.put_object` 上传图片字节，按 `{prefix}/{user_id}/{YYYYMMDD}/{quiz_id}/q{n}.png` 生成对象键，返回 `COS_PUBLIC_BASE_URL` 或默认 COS 域名 URL；测试上传参数、URL 拼接、上传异常返回空
- [x] 2.4 先补测试再实现：`attach_images(user_id, quiz, settings)` 编排 5 题并发（`ThreadPoolExecutor`，上限取 `image_max_concurrency`）、单题失败隔离、额度预留与失败退还、额度为 0 跳过、未配置跳过；测试全成功、部分失败、额度不足、额度为 0、配置缺失、服务异常不外抛
- [x] 2.5 确认 2.1–2.4 全部离线测试通过（不调用真实百炼/COS），并检查日志不包含 SecretKey/临时签名信息

## 3. 异步出题任务接入

- [x] 3.1 先补测试再实现：`create_job` 接受并持久化 `generate_images`；存在 `document_ids` 时强制为 false；测试首页 true/false、文档范围 true 被强制关闭、`params_json` 内容正确（`pytest -q tests/test_quiz_job_service.py tests/test_quiz_jobs_api.py`）
- [x] 3.2 先补测试再实现：`_run_job` 在 `generate_quiz` 成功后、`persist_quiz` 前调用 `attach_images`；配图服务抛异常时任务仍 completed；测试调用顺序、文档任务不调用、异常隔离
- [x] 3.3 先补测试再实现：确认 `quiz_jobs.result_json` 与 `quiz_sessions.questions_json` 均包含 `image_url`，历史详情 `get_detail` 原样返回；测试有图/无图题库落库与回读
- [x] 3.4 运行后端全量回归 `pytest -q`，确认既有出题、接地、知识库、答题、报告、金币、历史用例全部通过

## 4. 前端开关与展示

- [x] 4.1 扩展 `src/types/index.ts`（`Question.image_url?`、`QuizGenerateParams.generate_images?`）与 `src/services/api.ts` 参数透传；运行 `npx tsc --noEmit` 或构建确认类型通过
- [x] 4.2 首页 `src/pages/index/index.tsx` / `index.scss` 增加「生成配图」开关（默认关闭、含“每题一张、每日限额”说明），提交时传 `generate_images`，`ActiveJob` 持久化并在恢复轮询时恢复开关；构建后人工确认开关展示与提交参数
- [x] 4.3 答题页 `src/pages/quiz/index.tsx` / `index.scss` 在题干下方展示 `image_url`，点击 `Taro.previewImage`，`onError` 隐藏图片；构建后人工确认有图/无图两种题目布局
- [x] 4.4 报告页 `src/pages/report/index.tsx` / `index.scss` 新增「题目回顾」卡片，当前闯关与历史回看都展示题干、正确答案与可选配图；构建后人工确认历史回看含图/文档历史无图两种场景
- [x] 4.5 知识库页 `src/pages/bank/index.tsx` 确认不出现配图开关、创建任务不传 `generate_images`；构建后人工确认文档出题流程不变
- [x] 4.6 运行 `npm run build:weapp` 与 `npm run build:h5` 均成功，并在微信开发者工具/H5 预览中走通“首页开关 → 生成 → 答题看图 → 报告回顾”全流程

## 5. 真实服务冒烟与验收

- [x] 5.1 在 `backend/.env` 配置真实 `DASHSCOPE_API_KEY`、`COS_*`，先设 `ENABLE_IMAGE_GENERATION=false` 启动，确认既有出题/答题/报告无变化
- [x] 5.2 打开 `ENABLE_IMAGE_GENERATION=true`，从首页发起 5 题配图任务，确认任务 completed、题目带 5 个 `image_url`、URL 在百炼临时链接过期后仍可访问、`image_generation_usage` 当日计数为 5
- [x] 5.3 临时把 `IMAGE_DAILY_LIMIT` 调为 1 或 0 再发起任务，确认额度不足时只生成剩余数量、额度为 0 时无图且无提示、题目正常返回；验证跨日日期行可重新计数
- [x] 5.4 从我的知识库发起文档一键闯关，确认不生成配图、无开关、报告页题目回顾正常展示题干与答案
- [x] 5.5 记录上线检查项：COS 域名或自定义 CDN 域名需加入微信小程序「downloadFile 合法域名」；真实冒烟结束后恢复 `IMAGE_DAILY_LIMIT=100`

## Workflow follow-up

- 完成实现与验证后运行 `openspec validate add-question-images --strict`，确认规格与任务一致。
- 经人工评审后再执行 `/opsx:archive` 归档本变更并同步主规格。
