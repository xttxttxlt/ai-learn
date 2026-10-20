# Tasks

## 1. 依赖、配置与数据库

- [x] 1.1 在 `backend/requirements.txt` 增加 `langchain-chroma`、`langchain-community`、`langchain-text-splitters`、`chromadb`、`pypdf`、`docx2txt`、`unstructured[md]`、`python-multipart`；安装后用 `.venv/Scripts/python.exe -c "import chromadb, langchain_chroma; from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader, UnstructuredMarkdownLoader, TextLoader; from langchain_text_splitters import RecursiveCharacterTextSplitter; print('ok')"` 验证导入成功。
- [x] 1.2 在 `backend/app/core/config.py` 增加知识库开关、百炼 Embedding、Chroma/上传目录、分块与检索参数；相对路径以 `backend/` 为基准解析。验证：新增 `tests/test_knowledge_base_config.py` 覆盖默认值、相对/绝对路径解析与 key 缺失判定，`pytest tests/test_knowledge_base_config.py -q` 通过。
- [x] 1.3 更新根目录 `.gitignore` 忽略 `backend/data/`，并核对 `backend/.env` / `.env.example` 已包含 `DASHSCOPE_API_KEY`、`EMBEDDING_*`、`ENABLE_KNOWLEDGE_BASE`、`CHROMA_PERSIST_DIR`、`KB_*` 占位项；验证：`grep -n "backend/data" .gitignore` 与 `grep -oE '^[A-Z_]+=' backend/.env.example | sort` 输出符合预期。
- [x] 1.4 在 `sql/init_mysql.sql` 新增 `knowledge_documents` 表（字段中文 COMMENT、索引、用户外键级联），并新增 `sql/migrations/20261020_add_knowledge_base.sql`（`IF NOT EXISTS` + 回滚语句）。验证：迁移脚本可在本地 MySQL 重复执行两次不报错，且 `SHOW CREATE TABLE knowledge_documents` 含中文注释与外键；确认未修改既有表。

## 2. 文档仓储层（TDD）

- [x] 2.1 先写 `backend/tests/test_knowledge_document_repository.py`：覆盖创建/查询/状态更新/列表/聚合统计/删除/启动清理，所有查询带 `user_id`。先确认测试失败（红），再实现 `app/repositories/knowledge_document_repository.py`（绿）；验证：`pytest tests/test_knowledge_document_repository.py -q` 全部通过。
- [x] 2.2 在 `app/utils/id_generator.py` 增加 `generate_doc_id()` 并与现有 ID 风格一致；验证：更新 `tests/test_id_generator.py`，断言前缀、唯一性与长度，测试通过。

## 3. 文档解析、分块与向量层（TDD）

- [x] 3.1 先写 `backend/tests/test_document_parser.py`：覆盖 PDF 页码、DOCX、Markdown、`.txt` 解析、空文档、分块大小/重叠、metadata（user/doc/doc_name/chunk_index/page）与分块上限。再实现 `app/llm/document_parser.py`；验证：`pytest tests/test_document_parser.py -q` 通过，且测试中不访问网络。
- [x] 3.2 先写 `backend/tests/test_knowledge_vector_store.py`：用 `tmp_path` 与确定性假 Embedding 验证 add/search、余弦相关度排序、`doc_id` 范围过滤、跨用户隔离、删除文档、重新实例化后仍可检索。再实现 `app/llm/knowledge_base.py` 中的 Embedding 工厂与 `KnowledgeVectorStore`；验证：`pytest tests/test_knowledge_vector_store.py -q` 通过。
- [x] 3.3 为 Embedding 工厂增加配置缺失、维度不一致、批量超限的测试（注入假客户端，不调用百炼）；验证：相关单测通过，异常信息可读且不泄露密钥。

## 4. 异步建库服务与知识库 API（TDD）

- [x] 4.1 先写 `backend/tests/test_knowledge_ingestion_service.py`：覆盖 `pending→processing→ready`、解析失败/空文档/超分块/Embedding 失败进入 `failed`、启动清理、建库期间文档被删除时放弃写入并清理向量。再实现 `app/services/knowledge_ingestion_service.py`；验证：`pytest tests/test_knowledge_ingestion_service.py -q` 通过。
- [x] 4.2 先写 `backend/tests/test_knowledge_base_service.py`：覆盖统计与文档列表、删除文档（向量/文件/记录）、越权返回未找到、`validate_document_scope`（存在、归属、全部 ready）。再实现 `app/services/knowledge_base_service.py`；验证：`pytest tests/test_knowledge_base_service.py -q` 通过。
- [x] 4.3 先写 `backend/tests/test_knowledge_base_api.py`：覆盖鉴权、统计/列表、multipart 上传（合法 `.md`/`.pdf`/`.docx`/`.txt`、错误扩展名、超大小、空文件）、轮询状态、删除、越权删除。再实现 `app/api/v1/routes/knowledge_base.py` 并注册到 `app/api/v1/router.py`；验证：`pytest tests/test_knowledge_base_api.py -q` 通过。
- [x] 4.4 在 `app/main.py` lifespan 中接入建库启动清理（仅清理 `pending/processing`）；验证：相关单测断言启动清理被调用，`pytest tests/test_knowledge_ingestion_service.py tests/test_health.py -q` 通过。

## 5. 出题 Agent 与异步任务集成（TDD）

- [x] 5.1 扩展 `app/models/quiz.py` 的 `Source`（`url` 默认空、`kind` 支持 `knowledge_base`、新增 `doc_id/chunk_index/page/snippet`）；先更新/新增来源抽取测试（联网来源回归 + 知识库来源去重排序），再扩展 `app/llm/quiz_agent.py::extract_sources_from_messages`。验证：`pytest tests/test_quiz_agent.py -q` 通过。
- [x] 5.2 先写 `backend/tests/test_knowledge_base_tool.py`：覆盖工具 content/artifact、空结果、检索异常、`document_ids` 范围与来源字段；再实现 `KnowledgeScope` 与 `build_knowledge_base_tool`，验证：`pytest tests/test_knowledge_base_tool.py -q` 通过。
- [x] 5.3 在 `app/prompts/quiz_prompt.py` 新增 `RESEARCH_PROMPT_WITH_KB`（首页自主路由与文档模式仅用当前文档两种规则），并给 `build_research_agent` 增加可选 `system_prompt` 参数（默认保持 V2）。验证：新增 prompt 契约测试断言工具名、两种模式规则与“不得编造出处”，`pytest tests/test_prompt_contract.py -q` 通过。
- [x] 5.4 改造 `app/services/quiz_service.py`：增加 `knowledge_scope`/`kb_tool`；首页模式装配知识库+联网工具并按“知识库+联网 → 仅联网 → 未接地”降级；文档模式仅装配知识库工具，最终无知识库来源时抛出可读错误；先写 `backend/tests/test_quiz_service_kb.py` 覆盖两种模式与降级，再实现；验证：`pytest tests/test_quiz_service_kb.py tests/test_quiz_service_grounding.py tests/test_quiz_service.py -q` 通过。
- [x] 5.5 改造 `app/services/quiz_job_service.py` 与 `app/models/quiz.py::QuizGenerateRequest`：支持 `document_ids`、创建前 `validate_document_scope`、params 透传、执行时构造 `KnowledgeScope`；无文档范围且无可用文档时保持 `generate_quiz(req)` 旧调用签名。验证：`pytest tests/test_quiz_job_service.py tests/test_quiz_jobs_api.py -q` 通过，并新增 `test_quiz_job_kb.py` 覆盖携带/越权/未就绪/执行期间文档失效/未携带范围。
- [x] 5.6 更新阶段二提示，使研究简报可来自“联网/网页抽取/个人知识库检索”，仍要求只依据简报事实；验证：`pytest tests/test_prompt_contract.py tests/test_report_prompt_contract.py -q` 通过，现有联网出题文案不回归。

## 6. 前端“我的知识库”页面（按截图 UI）

- [x] 6.1 扩展 `frontend/src/types/index.ts`（KnowledgeDocument/KnowledgeBaseOverview/Source 知识库字段/QuizGenerateParams 的 `document_ids`）与 `frontend/src/services/api.ts`（知识库统计与文档列表、上传、删除）；在 `request.ts` 增加 multipart 上传封装（不设置 JSON Content-Type、携带 token），验证：`npm run build:h5` 类型检查/构建通过。
- [x] 6.2 将 `frontend/src/pages/bank/index.tsx` 重写为“我的知识库”：顶部上传卡片（`+`、标题“上传文档建知识库”、副标题“支持 PDF / Word / Markdown / 文本，最大 10MB”）、空态引导、文档列表；验证：`npm run build:h5` 通过，Playwright 拦截知识库 API 验证上传卡片、空态与文档列表渲染。
- [x] 6.3 实现文档卡片：文件名、状态标签（已就绪/处理中/失败）、知识片段数（如“共 17 个知识片段”）、橙色“开始闯关”、灰色“删除”；验证：Playwright 用 ready/processing/failed fixture 验证状态与按钮展示，删除二次确认后调用删除接口。
- [x] 6.4 实现上传与轮询：微信 `chooseMessageFile` + H5 隐藏 file input（accept `.pdf,.docx,.md,.txt`），上传后每 10 秒轮询知识库接口直到没有处理中文档；验证：Playwright 在 H5 中用 `setInputFiles` 上传、拦截轮询返回 processing→ready，页面状态正确切换。
- [x] 6.5 实现“开始闯关”：调用 `createQuizJob`（`document_ids=[doc_id]`、文档主题 prompt、5 题、mixed），写入 `ail_active_job` 后在知识库页显示全屏 loading 并轮询任务，完成后 `Taro.navigateTo` 进入闯关页；验证：Playwright 拦截任务创建请求，断言请求体字段；确认 loading 期间 URL 仍在知识库页，完成后进入闯关页且任务缓存被清理。

## 7. 来源展示与前端回归

- [x] 7.1 改造 `frontend/src/pages/quiz/index.tsx` 与 `frontend/src/pages/report/index.tsx`：知识库来源显示“知识库”标签、文档名、页码、分块摘要且不渲染无效链接；联网来源保持原标题+链接；来源为空不展示；验证：构建通过，Playwright 用含两类来源的题库/详情 fixture 验证渲染与链接行为。
- [x] 7.2 确认首页未新增知识库选择器，未选文档时请求体不含 `document_ids`；验证：Playwright 拦截首页生成请求，断言旧字段不变；后端由测试覆盖“有可用文档时自动装配知识库工具”。
- [x] 7.3 检查题库页对网络错误、登录失败、后端未启动的提示与重试；验证：H5 中断网/拦截 500 时页面不崩溃且提示可读。

## 8. 集成验证

- [x] 8.1 运行 `cd backend && .venv/Scripts/python.exe -m pytest -q`，确认新增测试与全部既有测试通过。
- [x] 8.2 配置真实 `DASHSCOPE_API_KEY` 与可用 MySQL/后端后做冒烟：上传 PDF/Markdown/TXT → 轮询到 `ready` → 文档卡片“开始闯关” → 任务完成且题目依据该文档、`sources` 含文档出处；再验证首页普通出题仍可联网/使用个人知识库。无真实 key 时记录为“待配置验证”，不得伪造通过。
  - 结果（2026-10-20）：真实 key 冒烟通过。Markdown 上传后 ~1.3s 进入 ready（1 个分块）；文档出题完成 5 题，`sources` 仅含该文档的知识库来源；首页出题完成 5 题，来源同时包含知识库与联网搜索；删除文档成功。
- [x] 8.3 H5 端到端验证：构建并预览 `frontend/dist`，用 Playwright 走通“我的知识库 → 上传 → 处理中 → 已就绪 → 开始闯关 → 首页生成中 → 闯关页来源展示”；微信开发者工具文件选择能力无法自动化时，明确记录为手工验证项。
  - 结果（2026-10-20）：H5 + Playwright 拦截 API 已走通上传/轮询/状态/删除/开始闯关/首页轮询/闯关与报告来源展示；微信开发者工具的文件选择（`chooseMessageFile`）无法自动化，保留为手工验证项（`npm run build:weapp` 已通过）。
- [x] 8.4 运行 `openspec validate add-knowledge-base-rag --strict` 并检查变更产物完整；确认无需修改既有主规格（归档时再同步 delta）。
  - 结果：strict 校验通过；既有主规格未修改。

## 实现备注

- Markdown 解析改用 `TextLoader` + 轻量标记清洗：实测 `UnstructuredMarkdownLoader` 会下载 NLTK 资源并在离线环境阻塞，故不保留 `unstructured[md]` 依赖。
- 真实书籍验证：458 页 / 约 86 万字 PDF 切分为 1388 块，原 500 上限导致失败；`KB_MAX_CHUNKS_PER_DOC` 默认值调整为 2000。
- 首页自定义 TabBar 使用 `reLaunch` 而非 `switchTab`（项目未配置原生 tabBar），从知识库返回首页沿用同一导航方式。
- 2026-10-20 应用户要求进入 apply，实现与验证均已完成。

- 知识库状态轮询间隔调整为 10 秒；后端日志强制 UTF-8 并写入 `backend/logs/backend.log`（测试环境不写文件日志）；新增 `start-dev.bat` / `start-backend.bat` / `start-frontend.bat` 启动脚本。
- 微信上传改用 `formData.file_name` 传真实文件名，后端优先该字段并统一清洗；已修复既有测试 PDF 的 DB、磁盘文件与 Chroma 元数据名称。
- “开始闯关”改为知识库页内 loading 轮询，完成后直接进入答题页，不再跳回首页；H5 + Playwright 已验证该流程与上传表单字段。
- 大文档（676 条/1388 块）出题实测会做多轮知识库检索，原 `QUIZ_AGENT_RECURSION_LIMIT=16` 在模型输出简报前触发 `GRAPH_RECURSION_LIMIT`。现给研究 Agent 加 `ToolCallLimitMiddleware(run_limit=10)`，达到上限后拦截多余调用并让模型用已有资料收尾；递归上限升至 30。真实文档出题冒烟通过：5 题、8 条来源、全部来自当前文档。文档模式 Agent 异常改为“文档出题失败，请稍后重试”，仅在无该文档来源时提示“文档内容不可用，请重新上传”。
- 启动建表连接执行 DDL 前设置 `SET sql_notes = 0`，并将 SQL 中的 `TINYINT(1)` 改为 `TINYINT`；启动日志不再出现 “database/table already exists” 与整数显示宽度弃用提示。

## Workflow follow-up

- 实现完成并通过评审后，使用 OpenSpec archive 流程归档本变更。
