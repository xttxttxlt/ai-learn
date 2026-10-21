# Spec Delta

## ADDED Requirements

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
