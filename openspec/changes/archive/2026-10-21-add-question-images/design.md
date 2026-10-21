# Design

## Context

现有出题链路是异步任务：`POST /api/v1/quiz/jobs` 先落 `quiz_jobs`，后台 `_run_job` 调用 `generate_quiz`（DeepSeek + Tavily/知识库），成功后 `persist_quiz` 写 `quiz_sessions.questions_json`，再标记 completed；前端轮询任务并在 `pages/quiz` 答题、`pages/report` 复盘。题目以 Pydantic `Question` 建模，经 JSON 列原样存取，因此新增可选字段不需要改既有表。

外部能力方面：项目已有 `DASHSCOPE_API_KEY`（Embedding 在用）与 `httpx`，但没有安装 DashScope SDK；COS 也尚未接入。qwen-image-3.0 的官方同步接口返回 24 小时临时 URL，必须转存才能长期展示。

## Goals / Non-Goals

**Goals:**

- 在不改变既有出题/答题/报告/金币/历史链路的前提下，为首页出题追加可选配图。
- 配图相关的一切失败都不影响题目交付；文档出题永远不配图。
- 生图、转存、配额、前端展示均可离线单元测试，不需要真实调用百炼或 COS。

**Non-Goals:**

- 不做单题重新生成、图片人工审核、图片清理/生命周期管理、私有桶签名 URL 或图片代理。
- 不改题量/难度选择器，不新增独立设置页。
- 不为文档出题、历史列表缩略图提供配图。

## Decisions

### 1. 配图阶段放在异步任务内、题目生成之后

在 `quiz_job_service._run_job` 中，`generate_quiz` 返回后、`persist_quiz` 之前调用 `image_generation_service.attach_images`。理由：

- 生图 Prompt 依赖最终题目（题干/知识点/正确答案），必须在出题后；
- 配图 URL 要先写进 `quiz.questions` 再统一持久化，历史详情与断点续答自然携带；
- 只有异步任务入口，放在 job 层可以统一处理配额与失败隔离，不污染 `quiz_service.generate_quiz` 的纯出题职责。

备选方案：在 `generate_quiz` 内部生图（同步链路耦合外部 I/O、配额 DB 调用不便）；或单独再建一个配图任务（前端要轮询两次，复杂度高）。均不采用。

### 2. 直接调用百炼同步 HTTP 接口，不引入 DashScope SDK

官方同步接口（已用 Context7/官网核对）：

```http
POST {IMAGE_BASE_URL}/services/aigc/multimodal-generation/generation
Authorization: Bearer {DASHSCOPE_API_KEY}
Content-Type: application/json
```

```json
{
  "model": "qwen-image-3.0",
  "input": {"messages": [{"role": "user", "content": [{"text": "<prompt>"}]}]},
  "parameters": {
    "negative_prompt": "低分辨率，低画质，文字，字母，数字，水印，构图混乱",
    "size": "512*512",
    "n": 1,
    "prompt_extend": false,
    "watermark": false
  }
}
```

响应图片在 `output.choices[0].message.content[*].image`，链接约 24 小时过期。

选择 `httpx` 的理由：项目已依赖 httpx；避免新增 `dashscope` SDK 及其全局 `base_http_api_url` 状态；用 `httpx.MockTransport` 可完全离线测试。`IMAGE_BASE_URL` 默认 `https://dashscope.aliyuncs.com/api/v1`；若账号使用 3.0 的业务空间专属域名，可在 `.env` 覆盖为 `https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/api/v1`。`IMAGE_MODEL` 默认 `qwen-image-3.0`，可切 `qwen-image-3.0-pro`。

真实并发冒烟发现百炼会对突发请求返回 429，因此对 429/5xx 增加最多 3 次指数退避重试并加随机抖动，避免 5 个并发失败请求在同一时刻再次撞限流；单题最终失败仍只跳过该题。

### 3. 每题一次请求、5 题并发、512×512

qwen-image-3.0 单次 `n` 支持 1–6，但“每题一张且 Prompt 不同”无法用一次请求完成，因此每题独立 `n=1`。使用 `ThreadPoolExecutor`，并发数 `min(image_max_concurrency, 题数, 6)`，默认 `image_max_concurrency=6`。单请求 `image_timeout_seconds=45`，`prompt_extend=false` 降低延迟；整体配图阶段最坏约 45–90 秒，仍在既有 `quiz_job_timeout_seconds=300` 内。

### 4. Prompt 由题目字段确定性构建

`build_image_prompt` 取 `knowledge_point`、`stem`、正确答案对应选项文本，按固定上限截断（题干约 300 字、答案约 80 字），拼成中文学习卡片提示：

> 学习记忆卡片插图。主题：{知识点}。题目：{题干}。画面主体：{正确答案文本}。要求：主体明确、构图简洁、真实自然、适合学习记忆；不要出现任何文字、字母、数字、水印或边框。

不额外调用 LLM 生成 Prompt，避免增加一次模型调用与不确定性；图片直接呈现正确答案是产品预期（如单词配实物图）。若未来要避免“看图猜答案”，再增加“只画题干情境”的策略开关。

### 5. COS 公有读桶 + 固定 URL

用 `cos-python-sdk-v5` 的 `CosS3Client.put_object` 上传图片字节（`ContentType=image/png`，并显式设置 `ACL=public-read`，兼容桶默认私有但允许对象 ACL 的情况），对象键：

```
{cos_key_prefix}/{user_id}/{YYYYMMDD}/{quiz_id}/q{题号}.png
```

URL 优先使用 `COS_PUBLIC_BASE_URL`（自定义 CDN/域名），否则拼 `https://{COS_BUCKET}.cos.{COS_REGION}.myqcloud.com/{key}`。上传统一放在线程池任务里，和生图同一并发批次执行；密钥只读环境变量。

备选方案：私有桶 + 签名 URL。签名 URL 会过期，与“永久可访问”冲突，且需要额外代理接口，不采用。

### 6. 每日配额采用“预留 + 失败退还”

新增 `image_generation_usage(user_id, usage_date, image_count)`，唯一键 `(user_id, usage_date)`。流程：

1. 读取当日已用量，`remaining = image_daily_limit - used`；
2. `n = min(题数, max(0, remaining))`，先原子累加 `n`（预留额度）；
3. 只为前 `n` 题并发生成/转存；
4. 结束后把失败数量 `n - success` 退还（`GREATEST(0, image_count - x)`）。

这样并发任务同时预留时不会突破上限；进程在生成中途崩溃会留下已预留额度，最迟次日自动重置，属于可接受的保守行为。额度为 0 时直接跳过，不提示用户（按已确认的产品决策）。

用量读写放在 `image_usage_repository`，只做两条 SQL：`SELECT image_count ...` 与 `INSERT ... ON DUPLICATE KEY UPDATE image_count = image_count + VALUES(image_count)`；退还复用同一条带负数的累加，并在 SQL 中用 `GREATEST` 防负。

### 7. 失败隔离边界

- `attach_images` 对每个题目单独 `try/except`，失败只让该题 `image_url` 保持空；
- 配额读取/预留失败 → 跳过配图；
- 未配置 `ENABLE_IMAGE_GENERATION` 或缺少百炼 Key / COS 任一参数 → 跳过配图；
- `attach_images` 自身最外层再兜底捕获，`_run_job` 不因配图抛错；
- 所有异常只写结构化日志，不把外部服务错误写进 `quiz_jobs.error_message`。

### 8. 数据与接口兼容

- `Question.image_url: Optional[str] = None`，旧 JSON 反序列化不受影响；`questions_json` 不需要迁移。
- `QuizGenerateRequest.generate_images: bool = False`，`QuizJobCreateRequest` 自动继承；老客户端不传即为关闭。
- `create_job` 在存在 `document_ids` 时强制把 `generate_images` 置 false，并把最终值写入 `params_json` 与后台任务请求。
- 任务结果、`QuizDetail.questions` 无需新增字段，`image_url` 随题目模型自动透出。

### 9. 前端改动

- 首页：在输入框与「开始生成题目」之间加 `Switch` 行，默认关闭；`ActiveJob` 增加 `generate_images`，恢复轮询时同步恢复开关；提交时传给 `createQuizJob`。
- 答题页：在题干下方、选项上方渲染 `<Image mode="widthFix">`；点击 `Taro.previewImage`；`onError` 隐藏该图，不影响选项。
- 报告页：新增「题目回顾」卡片，数据来源分别为 `getCurrentQuiz().questions`（当前闯关）与 `getQuizDetail().questions`（历史回看）；逐题展示题干、正确答案文本、可选配图，点击图片预览。
- 知识库页：不新增开关，`createQuizJob` 不传 `generate_images`。

### 10. 配置项

```dotenv
# 题目配图（复用 DASHSCOPE_API_KEY）
ENABLE_IMAGE_GENERATION=true
IMAGE_BASE_URL=https://dashscope.aliyuncs.com/api/v1
IMAGE_MODEL=qwen-image-3.0
IMAGE_SIZE=512*512
IMAGE_TIMEOUT_SECONDS=45
IMAGE_MAX_CONCURRENCY=6
IMAGE_DAILY_LIMIT=100

# 腾讯云 COS（公有读桶）
COS_SECRET_ID=
COS_SECRET_KEY=
COS_REGION=
COS_BUCKET=
# 可选：自定义 CDN/域名，留空则用默认 COS 域名
COS_PUBLIC_BASE_URL=
COS_KEY_PREFIX=question-images
```

`Settings.image_generation_ready` 统一判断 `ENABLE_IMAGE_GENERATION + DASHSCOPE_API_KEY + COS 四项必填`，避免在业务代码里散落配置判断。

### 11. 测试策略（TDD）

- `tests/test_image_generation_service.py`：Prompt 内容与截断、响应 URL 解析、HTTP 失败返回 None、COS 上传参数与 URL 拼接、5 题全部成功、部分失败、配额预留/退还、额度为 0 不调用、未配置跳过、异常不外抛。
- `tests/test_image_usage_repository.py`：查询与累加 SQL/参数、负数退还使用 `GREATEST`。
- `tests/test_quiz_job_service.py`：`generate_images` 透传；文档范围强制关闭；配图服务异常时任务仍 completed；持久化与完成顺序。
- `tests/test_quiz_jobs_api.py`：创建请求接受 `generate_images` 并写入 `params_json`；文档范围请求最终不生成。
- 既有 282+ 测试全部回归；前端执行 `npm run build:weapp` 与 `npm run build:h5`。

## Risks / Trade-offs

- [qwen-image-3.0 地域/业务空间域名不一致] → `IMAGE_BASE_URL` 可覆盖；调用失败按单题降级并记录错误码，不阻断出题。
- [生图耗时拉长任务] → 5 题并发、`prompt_extend=false`、单请求 45 秒超时；配图阶段整体控制在约 1 分钟内。
- [图片可能直接呈现答案] → 这是“单词配实物图”的预期用法；若后续要避免，增加 Prompt 策略开关而非改数据结构。
- [公有读桶的访问控制] → 只上传题目配图，不含用户隐私；对象键含用户 ID 与随机 quiz_id，难以枚举；如后续收紧，可换私有桶 + CDN 鉴权。
- [配额并发超发] → 先预留后生成、失败退还；进程崩溃会暂时占用额度至次日，换取不超发。
- [微信小程序图片域名限制] → 部署时需把 COS 域名或自定义 CDN 域名加入小程序「downloadFile 合法域名」；H5 不受影响（写入上线检查清单）。
- [COS SDK 为同步调用] → 放在线程池内执行，与生图并发受 `image_max_concurrency` 约束，不阻塞事件循环。

## Migration Plan

1. 执行 `sql/migrations/20261021_add_image_generation.sql`（仅新增表，可重复执行）；`init_mysql.sql` 同步加入该表，供全新环境自动初始化。
2. `pip install -r backend/requirements.txt` 安装 `cos-python-sdk-v5`。
3. 在 `backend/.env` 填入 `COS_*` 与可选的 `IMAGE_*`；先保持 `ENABLE_IMAGE_GENERATION=false` 启动，确认既有出题链路无变化。
4. 打开开关，用 1 题/5 题各做一次真实冒烟：确认题库返回 `image_url`、URL 可直接访问、`image_generation_usage` 当日计数正确。
5. 回滚：将 `ENABLE_IMAGE_GENERATION=false` 即可立即停止生图；如需彻底回滚，可删除 `image_generation_usage` 表（题目中的 `image_url` 为可选字段，不影响旧链路）。
