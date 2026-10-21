# Proposal

## Why

当前闯关题目只有文字，学习英语单词、历史人物、地理地貌、动植物等强视觉内容时，用户需要在脑海中自行建立画面，记忆效率低。项目已具备百炼 API Key 与异步出题任务，适合在出题完成后为每道题追加一张与题干相关的配图，帮助用户把抽象知识绑定到具体画面上；这也是原需求文档中排在 P2 的多模态能力。

## What Changes

- 首页出题输入区新增「生成配图」开关（默认关闭），与「开始生成题目」放在同一区域；文档一键闯关（我的知识库）不提供开关，也不生成配图。
- 出题请求新增可选参数 `generate_images`（默认 `false`）。开启后，系统在题目生成完成后，根据每题题干、知识点与正确答案自动构建生图 Prompt，为每题生成一张 512×512 配图。
- 生图调用阿里云百炼 `qwen-image-3.0` 同步接口，5 道题并发生成（单次请求 `n=1`，接口最多支持 6 张）；单题生成失败只跳过该题，不影响题目返回。
- 生成结果（百炼返回 24 小时临时 URL）由后端立即下载并转存腾讯云 COS 公有读桶，题库中只保存 COS 永久 URL（`Question.image_url`），前端通过 URL 展示。
- 新增每人每日配图额度（默认 100 张，按成功转存图片计数）。额度用尽时本次不生成配图，题目正常返回、不做额外提示；跨天自动重置。
- 前端答题页在题干下方展示配图，支持点击预览；报告页新增「题目回顾」区域，展示题干、正确答案与配图，已完成历史回看也能看到图片。
- 配图能力不可用（未配置百炼/COS、生图失败、上传失败、额度不足）时静默降级：题库结构与答题流程保持不变，任务不会因配图失败而失败。
- 数据层只新增 `image_generation_usage` 一张用量表（含中文 COMMENT），不修改既有表；配图 URL 随题目写入既有 `questions_json`。新增 COS 与生图相关环境变量及 `cos-python-sdk-v5` 依赖。

## Capabilities

### New Capabilities

- `question-images`: 首页出题按题生成相关配图、生图 Prompt 构建、百炼同步生图与并发控制、COS 转存与永久 URL、每人每日配额、失败隔离、题目 `image_url` 透出，以及首页开关/答题页/报告页的前端展示。

### Modified Capabilities

- `quiz-generation`: 题目结构新增可选配图字段 `image_url`，不改变题目数量、题型、答案与校验规则；无配图时题目与旧版完全一致。
- `quiz-generation-jobs`: 出题任务请求新增可选 `generate_images` 参数；仅首页出题生效，文档范围任务强制不生成；配图阶段失败不改变任务的 completed / failed 判定。

## Impact

- 后端新增：`app/services/image_generation_service.py`（Prompt 构建、百炼同步生图、并发编排、失败隔离）、`app/services/cos_storage_service.py`（COS 上传与永久 URL）、`app/repositories/image_usage_repository.py`（每日用量读写）。
- 后端修改：`app/core/config.py`（生图/COS/配额配置与就绪判断）、`app/models/quiz.py`（`Question.image_url`、`QuizGenerateRequest.generate_images`）、`app/services/quiz_job_service.py`（任务参数透传、文档范围强制关闭、配图阶段接入）、`app/repositories/quiz_job_repository.py` 无结构变化（`params_json` 自然承载新字段）、`app/models/user.py` / `app/services/history_service.py` 无需改字段（历史详情随 `questions_json` 原样返回 `image_url`）。
- 数据库：`sql/init_mysql.sql` 新增 `image_generation_usage` 表；新增 `sql/migrations/20261021_add_image_generation.sql`（纯新增、可重复执行、附回滚语句）；不修改任何既有表。
- 前端（Taro 4.3 + React）：`src/pages/index/index.tsx` / `index.scss` 新增配图开关并随任务参数提交；`src/pages/quiz/index.tsx` / `index.scss` 展示题干配图与预览；`src/pages/report/index.tsx` / `index.scss` 新增题目回顾；`src/types/index.ts`、`src/services/api.ts` 扩展类型；`src/pages/bank/index.tsx` 保持不传配图参数。
- 依赖与环境：新增 `cos-python-sdk-v5`；复用现有 `DASHSCOPE_API_KEY` 与 `httpx`（不新增 DashScope SDK，直接调用官方同步 HTTP 接口）；新增 `IMAGE_*`、`COS_*` 环境变量并同步 `backend/.env`、`backend/.env.example`。
- 外部服务：阿里云百炼 qwen-image-3.0（同步生图，返回 24 小时临时 URL）；腾讯云 COS（公有读桶，永久 URL）。现有 DeepSeek、Tavily、Embedding/Chroma、答题与金币链路行为不变。
- 不在本次范围：题目编辑/重新生成单题配图、图片质量评分与重试、私有桶签名 URL/图片代理、历史列表缩略图、题库文档出题配图、图片内容审核、CDN 刷新与图片清理任务。
