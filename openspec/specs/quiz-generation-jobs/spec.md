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

系统 SHALL 允许创建出题任务时携带可选的文档范围（零个或多个文档标识）。携带范围时，系统 MUST 校验每个文档归属当前用户且状态为已就绪；不满足时 SHALL 拒绝创建任务并返回可读原因。文档范围任务 SHALL 仅使用所选文档出题且不使用联网来源，结果参考来源 SHALL 标注知识库文档出处；任务执行期间文档失效时 SHALL 失败并提示重新上传，不得用泛化知识替代。未携带范围时保持现有出题行为。

#### Scenario: 携带文档创建任务

- **WHEN** 用户携带一个或多个本人已就绪文档创建出题任务
- **THEN** 系统受理任务并记录文档范围，后台仅使用这些文档出题

#### Scenario: 文档越权或不存在

- **WHEN** 任务携带不存在或不属于当前用户的文档
- **THEN** 系统拒绝创建任务并返回未找到或无权访问，不创建任务记录

#### Scenario: 文档未就绪

- **WHEN** 任务携带的任一文档仍处于排队中、处理中或失败状态
- **THEN** 系统拒绝创建任务并提示文档尚未就绪

#### Scenario: 执行期间文档失效

- **WHEN** 文档范围任务开始后所选文档被删除或不再可用
- **THEN** 任务失败并提示文档不可用，请重新上传，不生成与文档无关的题目

#### Scenario: 结果区分来源

- **WHEN** 文档范围任务完成且题库引用了文档内容
- **THEN** 任务结果中的参考来源包含知识库来源标识与文档出处，可与联网来源区分

#### Scenario: 未携带文档范围

- **WHEN** 创建任务时未携带任何文档标识
- **THEN** 系统不执行文档范围校验，沿用现有首页出题行为

### Requirement: 出题任务支持配图参数

系统 SHALL 允许创建首页出题任务时携带可选布尔参数 `generate_images`，默认 `false`，并将该参数随任务持久化。任务完成后，题库结果 SHALL 通过各题的 `image_url` 字段透出配图；请求该参数后，任务创建、幂等、轮询与结果交付的既有契约 MUST 保持不变。

#### Scenario: 携带配图参数创建任务

- **WHEN** 用户创建出题任务并携带 `generate_images=true`
- **THEN** 系统受理任务并记录该参数，同一 `request_id` 重复提交仍返回同一任务

#### Scenario: 未携带配图参数

- **WHEN** 创建任务时未携带 `generate_images`
- **THEN** 按 `false` 处理，任务行为与未引入配图能力前一致

#### Scenario: 完成结果透出配图

- **WHEN** 开启配图的任务完成且部分题目生成成功
- **THEN** 查询任务结果时，成功配图的题目带 `image_url`，未成功的题目保持无图

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
