# Proposal

## Why

个人中心已经有 `avatar_url` 字段，但前端始终只显示昵称首字占位，用户无法使用微信头像；首页也看不到每日配图额度，只能在用满后被动发现图片没生成；同时经实测 MySQL `NOW()` 返回 UTC，现有各表 `DATETIME` 实际存的是 UTC，历史记录与更新时间的展示比北京时间慢 8 小时。三项问题都直接影响用户对个人资料、配图配额与历史时间的信任感，适合在本轮一起修正。

## What Changes

- 新增头像上传能力：个人中心点击头像可调起微信原生头像选择（`button open-type="chooseAvatar"`），后端校验图片后上传腾讯云 COS（公有读、永久 URL），并把 URL 写回 `users.avatar_url`；昵称使用微信 `input type="nickname"` 填写能力，沿用既有昵称更新接口。
- 头像在个人中心与首页问候区同步展示；未设置头像时保持现有昵称首字占位，布局尺寸不变。
- 头像上传失败只影响本次头像更新，保留旧头像；不影响登录、出题、答题、报告、知识库等既有链路。
- 用户档案接口新增当日配图额度信息（日期、已用、上限、剩余），首页「生成配图」区域展示“今日配图 x/100”；当日用满时只禁用配图开关，纯文字出题仍可正常使用；跨日按北京时间自然日自动重置。
- MySQL 连接会话统一设置北京时间（默认 `+08:00`），此后新增/更新的时间字段按北京时间写入；配额“当日”也改为显式按北京时间计算，不再依赖操作系统时区。
- 按已确认决策：**HISTORICAL 数据不回填**，已有记录的 UTC 时间保持原样，历史记录仍会比北京时间慢 8 小时；本次只保证新数据正确。不做 `BREAKING` 接口变更，不修改任何既有表结构。

## Capabilities

### New Capabilities

- `user-profile`: 用户头像上传与微信原生头像/昵称入口、COS 永久 URL 保存、个人中心与首页头像展示，以及头像失败时的降级边界。
- `data-timezone`: 数据库会话固定北京时间、新增时间字段的写入规则、配额“当日”的时区计算，以及旧数据不回填的明确边界。

### Modified Capabilities

- `question-images`: 增加每日配图额度的查询与前端展示要求：档案接口返回当日用量/上限/剩余，首页展示 x/100，额度用满时禁用配图开关但不阻断纯文字出题。

## Impact

- 后端新增：`app/api/v1/routes/user.py` 头像上传路由；`app/services/avatar_service.py`（图片校验、COS 转存、档案更新）；`app/services/cos_storage_service.py` 增加头像对象键与图片上传；`app/utils/time_utils.py`（北京时间工具）。
- 后端修改：`app/core/db.py`（连接会话时区与初始化连接时区）、`app/core/config.py`（`MYSQL_TIME_ZONE`、`COS_AVATAR_PREFIX`、头像大小上限等配置）、`app/services/user_service.py` / `app/models/user.py`（档案响应增加配图额度）、`app/services/image_generation_service.py`（按北京时间取当日）、`app/services/knowledge_base_service.py`（文档创建时间显式使用北京时间）、`app/repositories/image_usage_repository.py`（复用当日用量查询）。
- 前端（Taro 4.3 + React）：`src/pages/profile/index.tsx` / `index.scss`（头像选择、昵称输入、头像展示）、`src/pages/index/index.tsx` / `index.scss`（首页头像与“今日配图 x/100”、额度满禁用开关）、`src/services/api.ts`、`src/types/index.ts`。
- 数据库：不新增/修改表结构；头像复用 `users.avatar_url VARCHAR(500)`；时区修正仅通过连接会话配置生效，**不执行旧数据回填迁移**。
- 配置与依赖：新增 `MYSQL_TIME_ZONE`（默认 `+08:00`）、`COS_AVATAR_PREFIX`（默认 `avatars`）、`AVATAR_MAX_FILE_MB`（默认 2）等环境变量；复用已有 `cos-python-sdk-v5` 与 `python-multipart`，不新增依赖。
- 微信平台：需在小程序后台隐私保护指引中声明“收集你的昵称、头像”；`chooseAvatar` 与 `nickname` 输入最低基础库 2.21.2，需用户主动点击/输入，不静默读取。
- 不在本次范围：旧数据时间回填、历史头像文件清理/生命周期管理、头像裁剪/审核、自定义相册头像入口的额外 UI、配额购买或扩容、把数据库列改为 `TIMESTAMP`。
