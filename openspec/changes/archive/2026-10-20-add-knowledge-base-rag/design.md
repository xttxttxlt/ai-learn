# Design

## Context

动机与范围见 `proposal.md`，行为契约见 `specs/knowledge-base/spec.md`、`specs/quiz-generation/spec.md`、`specs/quiz-generation-jobs/spec.md`。当前实现约束：

- 出题是异步任务：`app/services/quiz_job_service.py` 创建 `quiz_jobs` 后，用 `run_in_threadpool(generate_quiz, req)` 执行；`app/services/quiz_service.py` 的接地路径是“研究 Agent（`create_agent` + Tavily 工具）产出研究简报 → `json_mode` 结构化链产出题库”，失败后降级到未接地链。
- `Quiz.sources` 已持久化到 `quiz_sessions.sources_json`，历史详情直接反序列化为 `Source`；本次只扩展 JSON 内字段，不改既有表结构。
- 用户系统已提供 JWT 强制鉴权；出题任务、历史、进度均按 `user_id` 隔离。
- 后端单进程部署（现有异步任务与启动清理都基于该假设）；测试用 `FakeDB` monkeypatch `app.core.db`，不连真实 MySQL。
- 前端 Taro 4.3 + React，首页已实现异步任务轮询与断点恢复；`bank` 页目前是“题库功能开发中”的占位页，Tab 文案为“题库”。
- 技术事实已通过 Context7 核对：
  - `chromadb.PersistentClient(path=...)` 持久化；`collection.delete(where={...})` 支持按元数据删除；`$in` 可用于多值过滤；`get_or_create_collection(..., configuration={"hnsw": {"space": "cosine"}})` 可配置余弦空间。
  - 百炼 OpenAI 兼容地址默认为 `https://dashscope.aliyuncs.com/compatible-mode/v1`；`text-embedding-v4` 支持 2048/1536/1024/768/512/256/128/64 维，默认 1024。
  - `OpenAIEmbeddings(model=..., base_url=..., dimensions=..., check_embedding_ctx_length=False)` 可对接非 OpenAI 的兼容端点；`check_embedding_ctx_length=False` 会发送原始文本，避免 tiktoken 发送 token 数组。
  - 文档加载器位于 `langchain_community.document_loaders`（`PyPDFLoader`、`Docx2txtLoader`、`UnstructuredMarkdownLoader`、`TextLoader`）；切分器位于 `langchain_text_splitters`（`RecursiveCharacterTextSplitter`）。

用户已拍板：**每个用户一个个人知识库，题库 Tab 即“我的知识库”**；**文档卡片“开始闯关”仅检索当前文档**；**一键使用文档名作为主题、默认 5 题混合难度**；**支持 PDF / Word(.docx) / Markdown / 纯文本(.txt)，最大 10MB**；**异步建库 + 状态轮询**。首页出题时，若已有可用文档，Agent 自动获得个人知识库检索能力并与联网自主路由；首页不新增选择器。

## Goals / Non-Goals

**Goals:**

- 把题库 Tab 变成可用的个人知识库：上传、状态、知识片段数、删除、文档一键闯关。
- 在不改动现有出题、答题、报告、金币、历史链路的前提下，新增个人知识库作为出题接地来源。
- 文档级出题只依据该文档，保证“上传什么就闯什么”；首页出题则保持 Agent 自主路由。
- 后端功能全部可离线测试（不依赖百炼/DeepSeek/Tavily 真实网络）。

**Non-Goals:**

- 多知识库/文件夹管理、知识库问答/聊天、文档在线预览、OCR、扫描件 PDF、`.doc`/PPT/图片/视频、团队共享与权限协作。
- 多文件一次上传、断点续传、文档版本管理、自动重建索引。
- 引入外部向量数据库、BM25/混合检索、重排模型或 LangGraph 自定义图。
- 修改现有 `quiz_sessions` / `quiz_jobs` 表结构或首页交互结构。

## Decisions

### 决策 1：数据模型与用户隔离

**选择：**

- 不新增知识库表。个人知识库是“每个用户一个”的隐式实体，题库 Tab 直接对应当前用户的文档集合。
- 新增 `knowledge_documents`：
  - `id`、`doc_id`（业务 ID，全局唯一）、`user_id`、`file_name`、`file_ext`、`file_size`、`file_path`、`status`（`pending` / `processing` / `ready` / `failed`）、`chunk_count`、`error_message`、`created_at`、`updated_at`、`finished_at`。
  - 索引：`(user_id, status)`、`(user_id, created_at)`；`user_id` 外键关联 `users.id`，`ON DELETE CASCADE`。
- 文档列表的汇总统计（总文档数、已就绪数、处理中数、失败数、总知识片段数）用聚合查询实时计算，不新增易漂移的计数字段。
- 向量库按图片方案：每个用户一个 Chroma collection，命名 `kb_user_{user_id}`；每个分块 metadata 携带 `user_id`、`doc_id`、`doc_name`、`chunk_index`、`page`（PDF 有则带）。不引入 `kb_id`。
- 所有仓储查询都必须带 `user_id`；跨用户访问统一返回 `NotFoundError`，不泄露资源是否存在。

**理由：** 题库 Tab 的交互是“一个知识库 + 多文档”，不需要知识库 CRUD；关系数据负责列表/状态/归属，向量数据负责检索，二者用 `doc_id` 关联，删除与隔离边界清晰。

**备选：** 保留多知识库表（用户已否决交互）；单 collection 全用户混存（隔离依赖过滤，误查风险高）。

### 决策 2：Embedding 接入方式

**选择：** 复用现有 `langchain-openai`，用 `OpenAIEmbeddings` 对接百炼 OpenAI 兼容接口：

```text
base_url = settings.embedding_base_url   # 默认 https://dashscope.aliyuncs.com/compatible-mode/v1
model = settings.embedding_model          # text-embedding-v4
dimensions = settings.embedding_dimensions  # 默认 1024，建库后不可变
api_key = settings.dashscope_api_key
check_embedding_ctx_length = False
chunk_size = settings.embedding_batch_size  # 默认 8，限制单请求批量
timeout / max_retries 复用配置
```

- Embedding 实例按配置缓存，避免每次检索重建。
- `dashscope_api_key` 为空时视为知识库服务不可用：上传接口返回可读错误；文档一键闯关在创建阶段拒绝并提示配置缺失。
- 维度变化会导致 Chroma 维度冲突，因此把 `embedding_dimensions` 视为建库期固定配置；变更需清空 `data/chroma` 重建。

**理由：** 与现有 DeepSeek 的 OpenAI 兼容接入方式一致，不新增 `dashscope` SDK 依赖；Context7 已确认该用法。`check_embedding_ctx_length=False` 是兼容端点能否接收原始中文文本的关键。

**备选：** `langchain_community.embeddings.DashScopeEmbeddings` / 官方 `dashscope` SDK（多一个依赖，且与现有 OpenAI 兼容层重复）；`text-embedding-v3`（用户已指定 v4）。

### 决策 3：文档解析、分块与异步建库

**选择：**

- 支持 `.pdf` / `.docx` / `.md` / `.txt`，大小上限默认 10 MB，单文档分块上限默认 2000（实测 458 页 / 约 86 万字书籍需 1388 块）。
- 解析器：
  - PDF：`PyPDFLoader(file_path)`，保留 `page` 元数据并转换为 1 基页码。
  - DOCX：`Docx2txtLoader(file_path)`。
  - Markdown：使用 `TextLoader(encoding="utf-8")` 读取并做轻量标记清洗（标题/列表/引用/链接/强调）。实施冒烟发现 `UnstructuredMarkdownLoader` 会尝试下载 NLTK 资源（`punkt_tab` 等），在离线/受限网络下阻塞数十秒；因 Markdown 本质是纯文本，统一走确定性文本解析，保证离线可用。
  - 纯文本：`TextLoader(file_path, encoding="utf-8")`。
- 切分：`RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100, add_start_index=True)`，分隔符优先 `\n\n`、`\n`、中文句号/问号/感叹号/分号/逗号、空格；过滤空白分块。
- 每个分块 metadata 写入 `user_id` / `doc_id` / `doc_name` / `chunk_index` / `page`（若有）。
- 上传接口只做“校验 + 落盘 + 建 `pending` 记录 + 调度后台任务”，立即返回；后台任务用 `asyncio.create_task` + 并发信号量（默认 2）执行，解析/Embedding/写 Chroma 通过 `run_in_threadpool` 执行。
- 状态流转：`pending → processing → ready` 或 `failed`；失败写入可读 `error_message`，内部堆栈只进日志。
- 启动时把残留 `pending` / `processing` 文档统一置为 `failed`（与 `quiz_job_service.cleanup_on_startup` 同风格），在 `main.py` lifespan 中调用。
- 删除与建库并发：后台任务在写向量前后都重新查询文档是否存在；若已被删除，则放弃写入并清理已写入的向量，避免孤儿数据。

**理由：** 上传请求保持短耗时，避免 PDF 解析 + 多次 Embedding 超过前端 60 秒请求时限；状态轮询与现有出题任务体验一致。

**备选：** 同步建库（大文件易超时、失败需重传）；消息队列/独立 worker（当前单进程部署过重）。

### 决策 4：Chroma 持久化与向量访问封装

**选择：** 在 `app/llm/knowledge_base.py` 封装 `KnowledgeVectorStore`：

- 模块级缓存一个 `chromadb.PersistentClient(path=chroma_persist_dir)`，所有用户共享 client，不同用户用不同 collection。
- collection 创建：`get_or_create_collection(name=f"kb_user_{user_id}", configuration={"hnsw": {"space": "cosine"}})`；collection 不存在时检索返回空而不是报错。
- 分块 ID 使用确定性 `f"{doc_id}:{chunk_index}"`；写入用 `collection.upsert`，保证重试幂等。
- 检索：`collection.query(query_embeddings=[embed_query(query)], n_results=top_k, where=... , include=["documents", "metadatas", "distances"])`。`where` 在指定文档范围时为 `{"doc_id": {"$in": document_ids}}`，全库检索时省略。余弦空间下 `score = max(0.0, 1 - distance)`。
- 删除：`collection.delete(where={"doc_id": doc_id})`；Chroma 删除是幂等的。
- 写入按 `embedding_batch_size` 分批 Embedding，再按小批次 `upsert`；整个过程受建库并发信号量约束。
- 测试注入 `client` 与 `embeddings`，使用 `tmp_path` 与确定性假向量，不访问外网。

**备选：** `langchain_chroma.Chroma` 包装器（添加/检索方便，但按 metadata 精确删除仍需访问底层 collection；距离到分数的转换也不直观）。因此只用 LangChain 的加载器、切分器与 Embedding，向量读写用 Chroma 原生 collection。

### 决策 5：检索工具、首页 Agent 路由与文档一键闯关

**选择：**

- 新增 `KnowledgeScope`（`user_id`、`document_ids: list[str]`）；`document_ids` 非空表示文档一键闯关，空表示首页全库模式。
- 新增 `build_knowledge_base_tool(scope, settings, store=None)`，返回 `StructuredTool(response_format="content_and_artifact")`，工具名 `search_knowledge_base`：
  - content：编号的相关分块摘要（文档名、页码、相关度、截断正文），供模型阅读。
  - artifact：结构化结果 `{results: [{doc_id, doc_name, chunk_index, page, snippet, score}]}`，供确定性抽取来源，杜绝模型编造。
  - 无结果返回 `[知识库无相关结果]` + 空 artifact；异常返回 `[知识库检索失败] ...` + 空 artifact。
- 工具装配规则：
  - **首页全库模式**（`document_ids` 为空）：当用户存在已就绪文档时，工具检索当前用户全部已就绪文档；同时保留 Tavily 联网工具，由 Agent 自主路由。没有已就绪文档时不加入知识库工具，保持原有行为。
  - **文档一键闯关模式**（`document_ids` 非空）：只加入限定到这些文档的知识库工具，不加入联网工具；确保“上传什么就闯什么”。
- `build_research_agent(llm, tools=None, system_prompt=RESEARCH_PROMPT_V2)` 增加可选 `system_prompt` 与 `tool_call_limit` 参数（默认值保持现有行为）；知识库模式传入 `RESEARCH_PROMPT_WITH_KB`：
  - 首页模式：私有/内部/题库类主题优先知识库；最新公开信息、知识库未覆盖时使用联网；可混合使用；简报标注事实来源。
  - 文档模式：只依据当前文档分块，不使用联网；文档信息不足时如实说明，不得编造。
  - 通过 `ToolCallLimitMiddleware(run_limit=10, exit_behavior="continue")` 限制单次研究的工具调用总数；达到上限后拦截多余调用并提示模型“不要再调用工具”，迫使模型用已检索内容输出简报；Agent 图递归上限相应升至 30。大文档实测：整书检索需要多轮，原 16 步会在模型收尾前触发 `GRAPH_RECURSION_LIMIT`。
- `generate_quiz` 增加可选 `knowledge_scope: KnowledgeScope | None = None` 与可注入的 `kb_tool`；`knowledge_scope` 存在时触发接地路径。
- 降级规则：
  - **首页模式**：知识库 + 联网 Agent 失败 → 仅联网 Agent（若联网可用）→ 现有未接地链；知识库检索为空不是失败，Agent 可改用联网。
  - **文档模式**：只接受基于该文档的知识库来源；Agent 执行失败（模型/递归/网络）返回“文档出题失败，请稍后重试”；最终没有任何该文档的知识库来源时返回“文档内容不可用，请重新上传”；均不降级到泛化出题。
- `grounded` 语义沿用“本次接地链路成功”即 true；文档模式只有取得该文档来源才算成功。

**理由：** 复用现有两阶段“研究 Agent + json_mode 结构化链”，DeepSeek 的结构化输出稳定性不变；工具 artifact 与 Tavily 工具同构，来源抽取逻辑可复用。首页保持 Agent 自主路由，文档按钮则提供确定性范围。

**备选：** 文档按钮仍允许联网/全库检索（会偏离“仅当前文档”的用户预期）；把检索写死在 `generate_quiz` 中（失去 Agent 自主性）。

### 决策 6：来源模型与历史兼容

**选择：** 扩展 `Source`（`app/models/quiz.py`）：

```text
title: str
url: str = ""                    # 知识库来源为空
score: float | None
kind: str | None                 # search / extract / knowledge_base
doc_id: str | None
chunk_index: int | None
page: int | None
snippet: str | None              # 截断到约 300 字
```

- `url` 由必填改为有默认值，现有联网来源构造方式不变。
- `extract_sources_from_messages` 扩展：
  - `search_knowledge_base` 的 artifact 转为 `kind="knowledge_base"`；
  - 去重键：联网按 URL，知识库按 `(doc_id, chunk_index)`；
  - 排序：知识库来源优先，随后网页抽取、联网搜索；组内按相关度降序；总数上限 8。
- `quiz_sessions.sources_json` 是 JSON 列，新增字段无需数据库迁移；历史详情与前端类型同步扩展即可。

**理由：** 不改既有表结构，联网来源完全兼容；知识库来源可追溯、不可被模型伪造。

### 决策 7：API 设计与错误语义

新增 `app/api/v1/routes/knowledge_base.py`，统一前缀 `/knowledge-base`，全部要求 JWT：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/knowledge-base` | 当前用户个人知识库统计 + 文档列表（前端轮询使用） |
| POST | `/knowledge-base/documents` | multipart 上传单文件，字段名 `file`，可选 `file_name` 传真实文件名 |
| DELETE | `/knowledge-base/documents/{doc_id}` | 删除文档并清理向量/文件 |

- 不提供知识库创建/重命名/删除接口：每位用户一个隐式知识库。
- 上传以流式方式写临时文件并累计字节数，超过上限立即中止并删除临时文件，避免整文件读入内存。
- 微信小程序 `Taro.uploadFile` 只能用临时文件路径作为 multipart 文件名，前端额外通过 `formData.file_name` 传真实文件名；后端优先使用该字段，缺省时回退到 `upload.filename`。
- 文件名只取 `Path(filename).name`（`file_name` 同样处理），防止路径穿越；显示名与保存名统一清洗，保存路径 `data/knowledge_base/{user_id}/{doc_id}/{safe_name}`。
- 新错误码：`4005` 知识库操作失败、`4006` 文档处理失败、`4007` 知识库服务未配置/不可用；越权/不存在统一用 `4040`，参数问题用 `4000`。
- 上传成功后返回 `status="pending"` 的文档对象；前端轮询知识库接口直到所有文档离开 `pending/processing`。

**理由：** 单接口同时返回统计与文档，减少前端轮询复杂度；错误码与现有 `AppError` 风格一致。

### 决策 8：出题任务扩展与兼容保护

**选择：**

- `QuizGenerateRequest` 增加 `document_ids: list[str] = Field(default_factory=list)`（最多 10 个）；`QuizJobCreateRequest` 继承该字段。
- `create_job` 只在 `document_ids` 非空时执行文档范围校验：每个文档存在、归属当前用户且状态为 `ready`；校验失败不创建任务。校验逻辑放在 `knowledge_base_service.validate_document_scope`，便于单测。
- `params_json` 在非空时写入 `document_ids`；`_run_job` 构造 `KnowledgeScope(user_id, document_ids)`。
- **兼容保护**：`_run_job` 在没有文档范围且用户没有已就绪文档时，仍以 `generate_quiz(req)` 调用，不追加关键字参数，确保现有 monkeypatch 测试（`lambda req: quiz`）不受影响；只有存在文档范围或用户存在已就绪文档时才传 `knowledge_scope=...`。这里需要一次 `count_ready(user_id)` 查询。
- 文档范围任务执行中知识库被删除：任务失败并提示重新上传，不使用泛化知识。
- 任务结果中的 `sources` 已随 `Quiz` 序列化，知识库来源无需改 `quiz_jobs` 表。
- 前端文档一键闯关使用 `user_input = f"请根据我的文档《{doc_name}》生成闯关题目，覆盖文档核心知识点。"`，`document_ids=[doc_id]`，`question_count=5`，`difficulty="mixed"`。

**理由：** 所有改动均为可选路径；没有文档的用户与现在完全一致；文档按钮的范围确定性由 `document_ids` 保证。

### 决策 9：前端交互（按截图 UI）

- `pages/bank/index`（题库 Tab）直接作为“我的知识库”页面，不新增详情页：
  - 顶部标题“我的知识库”；
  - 上传卡片：大号 `+`、标题“上传文档建知识库”、副标题“支持 PDF / Word / Markdown / 文本，最大 10MB”；
  - “我的文档”列表：每张卡片展示文件名、状态标签（已就绪/处理中/失败）、知识片段数（如“共 17 个知识片段”）、橙色“开始闯关”按钮、灰色“删除”按钮；
  - 空态展示上传引导；有处理中文档时每 10 秒轮询 `GET /knowledge-base`；
  - 上传：微信环境用 `Taro.chooseMessageFile({count:1, type:"file", extension:["pdf","docx","md","txt"]})`；H5 环境用隐藏 `<input type="file" accept=".pdf,.docx,.md,.txt">` 触发同一上传流程；上传后用 `Taro.uploadFile` 携带 `Authorization` 头与 `formData.file_name`，并解析 `{code,message,data}`。
- “开始闯关”流程：
  1. 调用 `createQuizJob`，携带 `document_ids=[doc_id]`、文档主题 prompt、5 题、mixed；
  2. 把任务写入现有 `ail_active_job` 本地存储；
  3. **停留在知识库页**，显示全屏 loading（文档名 + “AI 正在出题”），页内按任务节奏轮询 `GET /quiz/jobs/{job_id}`；
  4. 完成后清理本地任务并 `Taro.navigateTo` 进入闯关页；失败或超时关闭 loading，在当前页提示可读原因，可再次点击该文档的“开始闯关”；
  5. 页面隐藏时暂停页内轮询，再次显示且本地仍有该页任务时自动恢复。
- 首页不改布局、不加知识库选择器；后端在用户存在已就绪文档时自动为 Agent 加入个人知识库工具，未选择文档时仍由 Agent 自主路由。
- 闯关页/报告页：
  - `kind === "knowledge_base"` 的来源展示“知识库”标签、文档名、页码、分块摘要，不渲染无效链接；
  - 联网来源沿用现有标题 + 链接展示；来源为空时不展示区域。
- `src/types/index.ts`、`src/services/api.ts` 增加知识库统计/文档类型、列表、上传、删除方法；`request.ts` 增加 multipart 上传封装（不设置 JSON Content-Type）。
- 不新增页面、不改 `app.config.ts` 的页面列表；样式复用现有卡片/列表风格。

### 决策 10：配置、依赖与运维

新增配置（`app/core/config.py`，`.env.example` / `.env` 已写入）：

```text
ENABLE_KNOWLEDGE_BASE=true
DASHSCOPE_API_KEY=...
EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_DIMENSIONS=1024
EMBEDDING_BATCH_SIZE=8
EMBEDDING_TIMEOUT=30
EMBEDDING_MAX_RETRIES=2
CHROMA_PERSIST_DIR=data/chroma
KB_UPLOAD_DIR=data/knowledge_base
KB_MAX_FILE_MB=10
KB_CHUNK_SIZE=800
KB_CHUNK_OVERLAP=100
KB_MAX_CHUNKS_PER_DOC=2000
KB_RETRIEVAL_TOP_K=4
KB_INGESTION_CONCURRENCY=2
QUIZ_AGENT_TOOL_CALL_LIMIT=10
QUIZ_AGENT_RECURSION_LIMIT=30
```

- 相对路径统一以 `backend/` 为基准解析；启动/首次使用时创建目录。
- `.gitignore` 忽略 `backend/data/`。
- 新增依赖：`langchain-chroma`、`langchain-community`、`langchain-text-splitters`、`chromadb`、`pypdf`、`docx2txt`、`python-multipart`（FastAPI 文件上传）。Markdown 不再依赖 `unstructured[md]`（避免 NLTK 资源下载阻塞）。
- 迁移脚本 `sql/migrations/20261020_add_knowledge_base.sql` 纯新增 `knowledge_documents` 表、`IF NOT EXISTS`、附回滚语句；`sql/init_mysql.sql` 同步建表。**不改动任何既有表。**

### 决策 11：测试策略（TDD）

- 后端按“先写失败测试，再实现”推进；全部测试不访问真实百炼/DeepSeek/Tavily：
  - 仓储/服务：`FakeDB` 验证 SQL 参数、归属校验、状态流转、统计、级联清理调用。
  - 解析/切分：临时文件 + monkeypatch loader，验证 PDF 页码、`.txt`/`.md` 文本、空文档、分块上限与元数据。
  - 向量层：`tmp_path` + `chromadb.PersistentClient` + 确定性假 Embedding，验证增删查、`doc_id` 过滤、跨用户隔离、重启后仍可检索。
  - 检索工具/Agent：验证工具 content/artifact、空结果、异常降级、知识库来源抽取与去重。
  - 出题服务：注入假 Agent/工具，验证首页模式知识库+联网工具装配、文档模式仅知识库工具、文档模式无来源时失败、首页模式回退顺序。
  - API：`TestClient` + multipart 上传，验证鉴权、格式/大小/空文件错误、统计与轮询、删除、越权。
  - 任务：验证携带文档创建、范围校验（不存在/越权/未就绪）、执行期间文档失效失败、未携带范围时调用签名不变。
- 回归：现有 `backend/tests` 全量通过，尤其是 `test_quiz_service_grounding.py`、`test_quiz_agent.py`、`test_quiz_job_service.py`、`test_quiz_jobs_api.py`、`test_prompt_contract.py`。
- 前端：`npm run build:h5` 通过；用 H5 构建 + Playwright 拦截 API 验证“我的知识库”上传卡片、文档状态、开始闯关、删除、来源展示；微信端文件选择能力以构建产物与类型检查为准（本机无法自动化微信开发者工具）。

## Risks / Trade-offs

- [百炼 Embedding 延迟/限流导致建库慢或失败] → 异步任务、批量大小可配、失败状态可读、失败后删除重传；单文档大小与分块数双重上限。
- [Chroma 与单进程异步任务的并发写] → 共享一个 `PersistentClient`、建库并发默认 2、分块批量 upsert；异常记录日志并将文档置失败。
- [删除与建库并发产生孤儿向量] → 写前/写后二次检查文档存在性，删除后清理该文档向量；删除操作幂等。
- [扫描版 PDF 无文本] → 解析后无内容直接失败并提示“未提取到可用文本”，不静默生成空库。
- [`unstructured` 在 Windows/Python 3.10 安装体积或依赖问题] → 已实测：Markdown 解析会触发 NLTK 资源下载并阻塞；改为 `TextLoader` + 轻量标记清洗，规格不变（Markdown 是纯文本）。
- [文档一键闯关时 Agent 未调用知识库工具] → 文档模式只提供知识库工具、系统提示要求只依据文档；执行后校验必须存在知识库来源，否则任务失败，杜绝泛化出题。
- [首页 Agent 未使用个人知识库] → 工具描述与系统提示明确知识库适用场景；观测工具调用轨迹。路由质量最终依赖真实模型，单测只验证工具装配与降级。
- [知识库分块注入导致 token 膨胀] → `KB_RETRIEVAL_TOP_K` 默认 4、单条摘要截断、研究简报长度沿用现有上限。
- [Embedding 维度变更导致 Chroma 维度冲突] → 维度作为建库期固定配置；变更需清空向量目录重建，写入文档说明。
- [前端 H5 与微信文件选择差异] → 双路径上传封装；微信用 `chooseMessageFile`，H5 用 `<input type=file>`；两者共用同一后端接口。
- [现有测试因新增可选字段/参数变化而失败] → 所有新字段有默认值；`_run_job` 无文档范围且无可用文档时保持旧调用签名；新增路由不改变既有路由。

## Migration Plan

1. 依赖与配置：更新 `requirements.txt`、`.env.example`、`.env`、`.gitignore`；安装依赖并做 `langchain-chroma` / document loaders / `unstructured` 导入冒烟。
2. 数据库：执行新增 `knowledge_documents` 表迁移；确认既有表无变化。
3. 后端（TDD）：先写仓储/服务/向量层/检索工具/出题集成/任务/API 测试，再实现；最后跑全量 `pytest`。
4. 前端：重写 `bank` 页为“我的知识库”，扩展类型与服务，兼容来源展示；`npm run build:h5` + Playwright 验证。
5. 灰度：先 `ENABLE_KNOWLEDGE_BASE=false` 部署，确认现有出题/历史/报告无回归；再配置 `DASHSCOPE_API_KEY` 打开开关，依次验证“上传 PDF/MD/TXT → 等待已就绪 → 文档开始闯关 → 首页普通出题 → 来源展示”。
6. 回滚：设 `ENABLE_KNOWLEDGE_BASE=false` 即可停用；题库页显示不可用提示，现有出题链路不受影响。需要彻底回滚时执行迁移脚本末尾的 `DROP TABLE`（先确认无保留需求），并手动清理 `backend/data/chroma`、`backend/data/knowledge_base`。既有表无迁移，无需回滚。

## Open Questions

- 单文件 10 MB、单文档 2000 分块、检索 top-k 4 为初值：实测 458 页 / 约 86 万字 PDF 为 1388 块，原 500 上限不足，故上调；上线后可按真实文档与成本继续调整（均配置化，不影响规格）。
- 知识库来源摘要在前端展示的截断长度（设计取约 200–300 字），可按 UI 效果微调。
- 百炼 Embedding 的实际批量上限与限流阈值需用真实 key 冒烟后确认，`EMBEDDING_BATCH_SIZE` 默认 8 可下调。
