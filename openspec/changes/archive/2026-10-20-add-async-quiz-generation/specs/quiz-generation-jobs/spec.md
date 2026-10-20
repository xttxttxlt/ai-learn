# Spec Delta

## Purpose

定义异步出题任务的生命周期：任务的创建与幂等、后台执行与状态流转、状态查询与结果交付、超时与重启兜底，使耗时的联网接地出题不再阻塞客户端请求，结果可被可靠取回。

## ADDED Requirements

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