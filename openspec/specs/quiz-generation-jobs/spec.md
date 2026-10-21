# quiz-generation-jobs Specification

## Purpose

定义异步出题任务的生命周期：任务的创建与幂等、后台执行与状态流转、状态查询与结果交付、超时与重启兜底，使耗时的联网接地出题不再阻塞客户端请求，结果可被可靠取回。

## Requirements

### Requirement: 任务创建与幂等

系统 SHALL 提供创建出题任务的接口：校验通过后先持久化任务再立即返回任务标识与进行中状态，请求内 MUST NOT 等待出题完成。同一用户以相同 request_id 重复提交时，系统 SHALL 返回已存在的任务而不重复出题。

#### Scenario: 创建成功立即返回

- **WHEN** 用户提交有效的出题请求（内容、题量、难度合法）
- **THEN** 系统持久化任务并在极短时间内返回任务标识与进行中状态，出题在后台继续

#### Scenario: 重复提交幂等

- **WHEN** 同一用户以相同 request_id 重复提交出题请求
- **THEN** 系统返回首次创建的任务标识，不创建第二个任务、不重复出题

#### Scenario: 校验失败不建任务

- **WHEN** 请求内容为空、超长或包含不允许的内容
- **THEN** 系统直接返回校验错误，不创建任何任务

### Requirement: 任务状态查询与结果交付

系统 SHALL 提供按任务标识查询的接口，返回 pending / running / completed / failed 之一。completed 时 SHALL 交付与既有结构契约一致的题库（含题量、题型、接地标记与参考来源）；failed 时 SHALL 返回可展示给用户的错误说明。查询 SHALL 仅限任务归属用户。

#### Scenario: 进行中查询

- **WHEN** 任务尚未完成时被查询
- **THEN** 返回 pending 或 running 状态，不包含题库数据

#### Scenario: 完成查询

- **WHEN** 任务完成后被查询
- **THEN** 返回 completed 状态与题库，题库满足既有的题量、题型与字段结构要求

#### Scenario: 失败查询

- **WHEN** 任务失败后被查询
- **THEN** 返回 failed 状态与可展示的错误说明，不包含异常堆栈等内部细节

#### Scenario: 越权查询不泄露

- **WHEN** 非归属用户查询他人的任务
- **THEN** 系统返回未找到，不泄露任务是否存在及其内容

### Requirement: 后台执行与状态流转

系统 SHALL 在后台执行任务，状态沿 pending → running → completed 或 failed 单向流转。成功完成时 SHALL 按既有规则持久化题库并与任务关联；出题本身成功而持久化失败时，任务 SHALL 仍标记为 completed 并可交付题库，持久化失败仅记录日志。

#### Scenario: 成功流转

- **WHEN** 后台出题与持久化流程完成
- **THEN** 任务状态转为 completed，题库可被查询取回

#### Scenario: 落库失败不影响交付

- **WHEN** 出题成功但题库持久化失败
- **THEN** 任务仍转为 completed 且题库可返回给用户，失败仅记录日志

#### Scenario: 失败流转

- **WHEN** 出题在重试后仍失败
- **THEN** 任务转为 failed 并记录可读的错误摘要

### Requirement: 超时与重启兜底

系统 SHALL 保证任务不会无限停留在进行中状态：running 超过约定时限（5 分钟）的任务 SHALL 被置为 failed；应用启动时 SHALL 将残留的 pending / running 任务置为 failed。

#### Scenario: 超时回收

- **WHEN** 任务处于 running 状态超过 5 分钟
- **THEN** 任务被置为 failed，用户可得到失败结论并重试

#### Scenario: 重启清理

- **WHEN** 应用重启后数据库中仍存在 pending 或 running 的残留任务
- **THEN** 这些任务在启动时被统一置为 failed

### Requirement: 出题任务支持文档范围

系统 SHALL 允许创建出题任务时携带可选的单个文档标识 `document_id` 与知识库开关 `use_knowledge_base`。仅当 `use_knowledge_base=true` 时，系统 MUST 校验该文档归属当前用户且状态为已就绪；不满足时 SHALL 拒绝创建任务并返回可读原因。知识库任务 SHALL 仅使用该文档出题且 MUST NOT 使用联网来源或其他文档；文档在执行期间失效时 SHALL 失败并提示重新上传，不得用泛化知识替代；文档有效但无相关内容时 SHALL 降级为通用出题。未开启知识库时 MUST NOT 解析或检索文档范围。

#### Scenario: 携带文档创建任务

- **WHEN** 用户携带一个本人已就绪文档且 `use_knowledge_base=true` 创建出题任务
- **THEN** 系统受理任务并记录该文档，后台仅使用该文档出题

#### Scenario: 文档越权或不存在

- **WHEN** 任务携带不存在或不属于当前用户的文档
- **THEN** 系统拒绝创建任务并返回未找到或无权访问，不创建任务记录

#### Scenario: 文档未就绪

- **WHEN** 任务携带的文档仍处于排队中、处理中或失败状态
- **THEN** 系统拒绝创建任务并提示文档尚未就绪

#### Scenario: 执行期间文档失效

- **WHEN** 知识库任务开始后所选文档被删除或不再可用
- **THEN** 任务失败并提示文档不可用，请重新上传，不生成与文档无关的题目

#### Scenario: 文档无相关内容降级通用

- **WHEN** 知识库任务执行时文档有效，但未检索到与主题相关的内容
- **THEN** 任务完成并交付未接地通用题库，grounded 为 false、参考来源为空

#### Scenario: 未携带文档范围

- **WHEN** 创建任务时 `use_knowledge_base=false`
- **THEN** 系统不解析、不校验也不检索任何文档范围

#### Scenario: 结果区分来源

- **WHEN** 知识库任务完成且题库引用了文档内容
- **THEN** 任务结果中的参考来源包含知识库来源标识与文档出处，可与联网来源区分

### Requirement: 出题任务支持配图参数

系统 SHALL 允许创建首页出题任务时携带可选布尔参数 `generate_images`，默认 `false`，并将该参数随任务持久化。任务完成后，题库结果 SHALL 通过各题的 `image_url` 字段透出配图；请求该参数后，任务创建、幂等、轮询与结果交付的既有契约 MUST 保持不变。当 `use_knowledge_base=true` 时，系统 MUST 忽略 `generate_images` 并按不配图执行。

#### Scenario: 携带配图参数创建任务

- **WHEN** 用户创建出题任务并携带 `generate_images=true`
- **THEN** 系统受理任务并记录该参数，同一 `request_id` 重复提交仍返回同一任务

#### Scenario: 未携带配图参数

- **WHEN** 创建任务时未携带 `generate_images`
- **THEN** 按 `false` 处理，任务行为与未引入配图能力前一致

#### Scenario: 完成结果透出配图

- **WHEN** 开启配图的任务完成且部分题目生成成功
- **THEN** 查询任务结果时，成功配图的题目带 `image_url`，未成功的题目保持无图

#### Scenario: 知识库任务忽略配图参数

- **WHEN** 创建知识库任务且请求携带 `generate_images=true`
- **THEN** 系统不调用生图服务，任务结果中所有题目均无图片 URL

### Requirement: 文档范围任务强制不配图

当出题任务携带文档范围时，系统 MUST NOT 生成配图，无论请求中的 `generate_images` 取何值；此类任务的结果 MUST NOT 包含配图 URL。文档范围任务的出题、来源标注与失败语义 SHALL 保持既有行为不变。

#### Scenario: 文档任务忽略配图参数

- **WHEN** 创建文档范围任务且请求携带 `generate_images=true`
- **THEN** 系统不调用生图服务，任务结果中所有题目均无图片 URL

#### Scenario: 文档任务既有行为不变

- **WHEN** 文档范围任务完成
- **THEN** 参考来源、题目结构与文档失效失败语义与未引入配图能力前一致

### Requirement: 配图阶段不影响任务终态

配图 SHALL 在题目生成成功后、任务标记 completed 前作为可选增强执行。任何配图相关失败 MUST NOT 将任务置为 failed，MUST NOT 阻止题库持久化或结果交付；任务仍 SHALL 转为 completed 并交付不含失败配图的题库。

#### Scenario: 配图阶段异常仍完成

- **WHEN** 题目生成成功但生图、下载、上传或配额存储出现异常
- **THEN** 任务转为 completed，题库正常返回，异常仅记录日志

#### Scenario: 全部配图失败

- **WHEN** 所有题目的配图都失败
- **THEN** 任务仍为 completed，题库结构与未开启配图时一致，不返回外部服务错误细节

### Requirement: 出题任务显式来源参数

创建出题任务 SHALL 接受 `use_web_search`、`use_knowledge_base` 与单个 `document_id`，默认分别为 false、false、null。`use_web_search` 与 `use_knowledge_base` MUST NOT 同时为 true；`use_knowledge_base=true` SHALL 要求 `document_id` 非空；`use_knowledge_base=false` 时 MUST NOT 携带 `document_id`。任务 SHALL 将三个参数随任务持久化，并在执行时按原值生效。

#### Scenario: 默认参数

- **WHEN** 客户端创建任务时未携带来源参数
- **THEN** 系统按不联网、不使用知识库处理，走未接地出题

#### Scenario: 互斥参数被拒绝

- **WHEN** 客户端同时提交 `use_web_search=true` 与 `use_knowledge_base=true`
- **THEN** 系统拒绝创建任务并返回可读的校验错误，不创建任务记录

#### Scenario: 知识库缺少文档被拒绝

- **WHEN** 客户端提交 `use_knowledge_base=true` 但未提供 `document_id`
- **THEN** 系统拒绝创建任务并提示需要选择文档

#### Scenario: 非知识库携带文档被拒绝

- **WHEN** 客户端提交 `use_knowledge_base=false` 但携带了 `document_id`
- **THEN** 系统拒绝创建任务并返回可读的校验错误

#### Scenario: 参数持久化

- **WHEN** 任务创建成功
- **THEN** 三个来源参数随任务保存，后台执行时使用保存的值，不读取创建后的全局默认变化

### Requirement: 出题任务阶段耗时埋点

系统 SHALL 为每个出题任务记录阶段耗时与关键计数，至少包含排队、文档范围解析、生成、研究、阶段二、配图、落库与总耗时，以及研究阶段的 LLM/工具调用次数、阶段二尝试次数、最终路径、grounded 与来源数量。记录 SHALL 在任务成功与失败时都可用于查询；耗时 SHALL 使用单调时钟计算，MUST NOT 依赖数据库时区或系统墙钟。

#### Scenario: 成功任务记录完整耗时

- **WHEN** 一个出题任务成功完成
- **THEN** 任务记录与结构化日志包含各已执行阶段耗时、总耗时、最终路径、LLM/工具调用次数与来源数量

#### Scenario: 失败任务记录已发生阶段

- **WHEN** 出题任务在生成或校验阶段失败
- **THEN** 任务记录仍包含已执行阶段耗时、总耗时与失败阶段标识，便于定位失败前后的耗时分布

#### Scenario: 全关路径耗时

- **WHEN** 用户未开启联网、知识库与配图
- **THEN** 记录中研究、阶段二附加轮次与配图耗时为 0 或省略，最终路径标记为未接地通用出题

#### Scenario: 知识库降级路径

- **WHEN** 知识库任务因无相关内容降级为通用出题
- **THEN** 记录中最终路径标记为知识库降级，并包含降级原因与知识库研究阶段耗时

#### Scenario: 单调时钟不受时区影响

- **WHEN** 数据库时区或系统墙钟发生变化
- **THEN** 任务耗时的计算与结果不受影响，仍为阶段间真实的单调时间差
