# Proposal

## Why

当前出题只能依赖 DeepSeek 自身知识或 Tavily 联网检索，无法覆盖企业内部培训资料、客服知识库、考试真题等私有内容——这些资料既不在模型训练数据里，也搜不到。新增“上传文档 → 个人知识库 → 基于文档出题”的 RAG 能力后，题库 Tab 不再只是占位页，用户可以直接把自己的资料变成可闯关的学习内容，应用范围从公开知识扩展到私域学习。

## What Changes

- 个人知识库：题库 Tab 升级为“我的知识库”，每个用户对应一个自己的知识库，无需创建/命名多个知识库；上传文档即建库，文档列表展示状态、知识片段数量与操作入口。
- 文档上传与异步建库：支持 PDF（`.pdf`）、Word（`.docx`）、Markdown（`.md`）与纯文本（`.txt`）单文件上传，大小上限 10 MB；上传后立即返回，后台完成解析、文本分块、`text-embedding-v4` 向量化并写入 Chroma；前端轮询文档状态（排队中/处理中/已就绪/失败），失败原因可读。
- 文档一键闯关：每张文档卡片提供“开始闯关”，仅检索当前文档，主题取文档名，默认 5 题、混合难度，直接创建异步出题任务并复用现有生成中/轮询/答题流程；文档失效或内容不可用时任务失败并提示重新上传，不用泛化知识代替。
- 首页出题自动接入个人知识库：当用户已有可用文档时，出题 Agent 同时持有个人知识库检索与 Tavily 联网工具，自主决定使用哪种来源；没有可用文档时完全保持现有联网/未接地行为，首页不新增知识库选择器。
- 知识库出处：题库 `sources` 支持 `kind="knowledge_base"` 来源（文档名、页码、分块摘要、相关度），与现有联网来源统一透出到闯关页与历史回看；`grounded` 在任何检索接地成功时为 true。
- 优雅降级：首页出题在知识库不可用/无相关内容时回退到联网或未接地链路，不中断出题；文档一键闯关则明确失败，避免生成与文档无关的题目。
- 数据与配置：只新增 `knowledge_documents` 一张表（含中文 COMMENT），不新增知识库表、不改任何既有表；新增 `DASHSCOPE_API_KEY`、Chroma 持久化目录、上传目录、分块与检索参数等配置；新增 `langchain-chroma`、`langchain-community`、`langchain-text-splitters`、`chromadb`、`pypdf`、`docx2txt`、`unstructured[md]`、`python-multipart` 依赖。

## Capabilities

### New Capabilities

- `knowledge-base`: 每个用户一个个人知识库的文档上传、格式与大小校验、异步解析/分块/Embedding、文档状态与列表、删除清理、用户级向量隔离、按文档范围的相关分块检索。

### Modified Capabilities

- `quiz-generation`: 出题新增个人知识库接地与文档一键闯关；首页出题由 Agent 在个人知识库与联网之间自主路由；题库透出知识库出处；无可用文档时保持原有行为。
- `quiz-generation-jobs`: 异步出题任务支持携带文档范围（可多个）；创建时校验文档归属与可用状态；文档范围任务仅使用所选文档且不使用联网，文档失效时明确失败。

## Impact

- 后端新增：`app/models/knowledge_document.py`、`app/repositories/knowledge_document_repository.py`、`app/services/knowledge_base_service.py`、`app/services/knowledge_ingestion_service.py`、`app/llm/knowledge_base.py`（Embedding/Chroma/检索工具）、`app/llm/document_parser.py`、`app/api/v1/routes/knowledge_base.py`。
- 后端修改：`app/api/v1/router.py`（注册路由）、`app/core/config.py`（Embedding/Chroma/上传/分块/检索配置）、`app/core/exceptions.py`（知识库相关业务错误码）、`app/models/quiz.py`（`Source` 扩展知识库字段、出题请求增加 `document_ids`）、`app/services/quiz_service.py`（知识库接地与 Agent 路由）、`app/services/quiz_job_service.py`（文档范围校验与任务透传）、`app/llm/quiz_agent.py` / `app/prompts/quiz_prompt.py`（Agent 工具与提示升级）、`app/services/history_service.py` / `app/models/user.py`（历史详情透出知识库来源）。
- 数据库：`sql/init_mysql.sql` 新增 `knowledge_documents` 表；新增 `sql/migrations/20261020_add_knowledge_base.sql`（纯新增、可重复执行、附回滚语句）；不新增知识库表，不修改 `quiz_sessions` / `quiz_jobs`。
- 前端（Taro 4.3 + React）：`src/pages/bank/index.tsx` 重写为“我的知识库”（上传卡片 + 文档列表 + 状态 + 开始闯关/删除），`src/pages/quiz/index.tsx`、`src/pages/report/index.tsx` 兼容知识库来源展示；`src/services/api.ts`、`src/services/request.ts`、`src/types/index.ts` 扩展；不新增知识库详情页，首页不新增知识库选择器。
- 依赖与环境：新增百炼 `text-embedding-v4` 调用（OpenAI 兼容接口，`DASHSCOPE_API_KEY`）；Chroma 本地持久化目录（默认 `backend/data/chroma`）；上传文件目录（默认 `backend/data/knowledge_base`）。`.env.example`、`.env`、`requirements.txt`、`.gitignore` 同步更新。
- 外部服务：阿里云百炼 Embedding API（需网络可达与有效 key）；现有 DeepSeek 与 Tavily 行为不变。
- 不在本次范围：多知识库/文件夹管理、知识库问答/聊天、`.doc`/PPT/图片/扫描件 OCR、视频解析、知识库共享/团队协作、向量库服务化部署、文档在线预览。
