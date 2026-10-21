# Design

## Context

- 用户表已有 `avatar_url VARCHAR(500)`，但前端个人中心与首页都只用昵称首字占位；`PUT /api/v1/user/profile` 已能更新昵称与头像 URL，缺少的是图片上传与展示链路。COS 已在题目配图中接入（`cos_storage_service`，公有读、`put_object` 显式 `ACL=public-read`）。
- 每日配图用量已落在 `image_generation_usage(user_id, usage_date, image_count)`，配额为“预留 + 失败退还”，但没有任何接口把当日用量暴露给前端。
- 实测本机 Windows 时间为北京时间 15:28 时，MySQL `NOW()` 为 07:28，`@@global.time_zone=SYSTEM` 实际是 UTC；现有 7 张表的 `created_at/updated_at/finished_at` 均为 UTC。用户已确认：**只修正新数据，不回填旧数据**。
- 微信已回收 `getUserProfile/getUserInfo` 的静默获取能力；官方推荐 `button open-type="chooseAvatar"` + `input type="nickname"`（已通过 Context7 核对微信与 Taro 4.3 文档）。
- aiomysql 的 `connect()/create_pool()` 支持 `init_command`，可在每条连接建立时执行会话级 SQL（已通过 Context7 核对）。

## Goals / Non-Goals

**Goals:**

- 用最小改动补齐头像上传、COS 持久化、个人中心/首页展示与微信原生头像/昵称入口。
- 在档案接口暴露北京时间当日配图额度，首页显示 x/100，额度满只禁用配图开关。
- 新写入的数据库时间统一为北京时间，且“当日”判断不依赖服务器操作系统时区。
- 所有新增后端逻辑可离线 TDD；头像/COS 失败、额度读取失败都不影响既有主链路。

**Non-Goals:**

- 不修正已有历史时间数据，不改变任何列类型，不新增时间相关表。
- 不做头像裁剪、审核、旧 COS 对象清理、CDN 刷新、图片代理。
- 不改动登录、出题、答题、报告、金币、知识库、断点续答的业务规则。

## Decisions

### 1. 时区：连接会话固定 `+08:00`，旧数据不回填

- `Settings` 增加 `mysql_time_zone: str = "+08:00"`（环境变量 `MYSQL_TIME_ZONE`）。
- `db.init_db()` 创建连接池时传入 `init_command=f"SET time_zone = '{settings.mysql_time_zone}'"`，保证池中每条连接建立后都先设置会话时区；`_run_schema_init()` 的独立连接同样带该 `init_command`。
- 这样 `CURRENT_TIMESTAMP`、`NOW()`、`ON UPDATE CURRENT_TIMESTAMP` 都会写入北京时间，且无需改表结构。命名时区依赖 MySQL 时区表，统一使用偏移量 `+08:00`（无夏令时）更稳。
- 旧数据按用户决策保持原值：部署前记录继续显示比北京时间慢 8 小时，不做 `UPDATE ... + INTERVAL 8 HOUR`。
- 混合数据的唯一相对时间比较是 `quiz_jobs.fail_if_timed_out`（`created_at < DATE_SUB(NOW(), INTERVAL n SECOND)`）。旧 UTC 行若仍处于 running 会被启动清理置 failed；变更后新建的任务两端都为北京时间，比较正确。因此不修改该 SQL。
- 备份方案（不采用）：改为 UTC 存储 + 接口展示时转换。会牵动所有时间格式化与前端，且无法同时兼容用户“旧数据不动”的要求。

### 2. 北京时间工具，替代 `date.today()` / 裸 `datetime.now()`

新增 `app/utils/time_utils.py`：

```python
BEIJING_TZ = timezone(timedelta(hours=8))

def beijing_now() -> datetime: ...
def beijing_today() -> date: ...
```

使用固定偏移而不是 `ZoneInfo("Asia/Shanghai")`，避免 Windows 缺少 tzdata 时运行期报错。替换点：

- `image_generation_service.attach_images`：`usage_date = today or beijing_today()`；
- `knowledge_base_service.upload_document` 返回的 `created_at`：`beijing_now()`；
- 新增配额查询：`beijing_today()` 作为 `usage_date`。

`image_generation_usage.usage_date` 由 Python 传入的 `date` 决定，与 MySQL 会话时区无关；因此即使服务器在 UTC，北京时间 00:00 后也会自然切换到新日期行，实现“每日 0 点重置”。

### 3. 头像上传由后端转存 COS，不接收前端直传 URL

- 新增 `POST /api/v1/user/avatar`（multipart `file`，已登录）。选择后端接收文件的原因：小程序 `chooseAvatar` 只给临时路径，前端直传 COS 需要把密钥或临时签名下发客户端；服务端转存可继续复用现有公有读桶与密钥管理。
- 校验：最多读取 `AVATAR_MAX_FILE_MB`（默认 2MB）+1 字节，按魔数识别 JPEG（`FF D8 FF`）、PNG（`89 50 4E 47 0D 0A 1A 0A`）、WebP（`RIFF....WEBP`）；空文件、超限、其他格式返回 `4000` 可读提示，不访问 COS、不改库。不新增 Pillow 依赖。
- COS 对象键：`{COS_AVATAR_PREFIX}/{user_id}/{YYYYMMDD}/{uuid}.{ext}`，默认前缀 `avatars`；每次上传生成新键，避免 CDN/客户端缓存旧图，旧对象暂不删除（生命周期清理不在本次范围）。`ContentType` 按识别结果设置，`ACL=public-read`。
- `cos_storage_service` 增加通用 `upload_bytes(data, key, settings, content_type)`；保留现有 `upload_image` 作为 PNG 包装，题目配图调用不变。COS 上传失败返回空串并由头像服务转成 `5001`，不抛到全局异常。
- 成功上传后再 `UPDATE users SET avatar_url=...`；数据库更新失败返回 `5001`，用户旧 `avatar_url` 保持不变，最多留下一个无引用 COS 对象（可接受）。
- 新增配置：`AVATAR_MAX_FILE_MB=2`、`COS_AVATAR_PREFIX=avatars`；`Settings.cos_ready` 统一判断 COS 四项必填，`image_generation_ready` 复用该属性。
- 接口成功返回完整 `ProfileOut`（含新头像和最新配图额度），前端一次更新头像、昵称缓存与额度。

### 4. 档案接口嵌套返回配图额度

`ProfileOut` 增加：

```json
"image_quota": {
  "usage_date": "2026-10-21",
  "used": 35,
  "limit": 100,
  "remaining": 65,
  "available": true
}
```

- `used` 取 `image_usage_repository.get_count(user_id, beijing_today())`；`limit` 取 `settings.image_daily_limit`；`remaining = max(0, limit - used)`。
- 配额查询异常时只影响该字段：`available=false`、`used=0`、`remaining=limit`，档案其他字段正常返回，前端显示“今日配图 暂不可用”且不阻断出题。
- 不新增独立配额接口，避免首页多一次请求；首页本来就在 `useDidShow` 拉取 `getProfile()`。

### 5. 前端头像组件与微信原生入口

- 新增 `src/components/UserAvatar`：`src` 非空时渲染 `<Image mode="aspectFill" onError>`，空值或加载失败回退昵称首字；`src` 变化时重置失败状态。个人中心与首页复用，保证尺寸与降级一致。
- 个人中心头像外层使用 `<Button className="user-card__avatar" openType="chooseAvatar" onChooseAvatar={...}>`；Taro 4.3 已支持 `openType` 与 `onChooseAvatar`。微信内由原生选择器返回 `detail.avatarUrl` 临时路径。
- 非微信环境（`process.env.TARO_ENV !== 'weapp'`）点击头像走 `Taro.chooseImage({count: 1})` 的相册/拍照入口，H5 构建与 Playwright 验证可用。
- 选图后调用 `uploadAvatar(filePath, fileName)`（复用 `uploadFile` multipart 封装），成功用返回的 `ProfileOut` 更新页面与 `setCachedUser`，失败 toast 且旧头像不变。
- 昵称改为个人中心内联编辑：点击“修改”后在原位置渲染 `<Input type="nickname" maxLength={20}>` 与保存/取消，利用微信键盘上方昵称提示；保存调用现有 `updateProfile({nickname})`。不再使用 `showModal(editable)`。若 Taro 类型未收录 `type="nickname"`，按现有代码风格做最小类型断言，构建时验证。
- 微信后台需在小程序隐私保护指引声明“收集你的昵称、头像”，代码层无需额外权限接口。

### 6. 首页配额展示与开关禁用

- `UserProfile` 类型增加 `image_quota`；首页从 `profile.image_quota` 计算：
  - `available=false` → “今日配图 暂不可用”；
  - 否则 → “今日配图 {used}/{limit}”；
  - `remaining <= 0` → 追加“今日配图额度已用完”，`Switch disabled`。
- 配额满只禁用配图 Switch；“开始生成题目”按钮仍可点击，`generate_images` 强制不提交或提交 false。纯文字出题完全不受影响。
- 刷新时机：`useDidShow` 已拉取档案；任务 completed 时额外触发一次非阻塞 `getProfile()`；`quotaFull` 变为 true 时把 `withImages` 置 false，避免恢复的任务状态与禁用开关矛盾。
- 北京时间 0 点后重新进入首页（或任务完成刷新）即可看到新额度；不额外做本地午夜定时器，避免页面常驻时的无意义轮询。

### 7. 测试策略（TDD）

先写失败测试再实现，覆盖：

- `test_db_init.py`：`init_db` 传给 `create_pool` 的 `init_command` 为 `SET time_zone = '+08:00'`；`_run_schema_init` 同样携带；`MYSQL_TIME_ZONE` 可覆盖。
- `test_time_utils.py`：固定 UTC 时刻下 `beijing_today()` 跨日行为正确（UTC 16:00 = 北京次日 00:00）。
- `test_avatar_service.py`：JPEG/PNG/WebP 魔数通过；GIF/空文件/超限拒绝；COS 键按用户与日期组织；上传失败不改库；数据库失败返回服务错误；成功返回新 URL。
- `test_user_api.py`：`POST /user/avatar` 需要鉴权；成功返回 `ProfileOut`；非法格式 4000；COS 未配置 5001；档案响应包含 `image_quota`；配额读取异常仍返回档案。
- `test_image_generation_service.py`：不传 `today` 时使用 `beijing_today()`（monkeypatch 验证），既有传入 `today` 的用例保持不变。
- 既有全量测试回归，确认登录、出题、异步任务、答题、报告、金币、历史、知识库、配图链路不受影响。
- 前端执行 `npm run build:weapp` 与 `npm run build:h5`；微信开发者工具验证头像选择/昵称输入/首页额度展示，额度满用 mock 或临时调小 `IMAGE_DAILY_LIMIT` 验证开关禁用。

## Risks / Trade-offs

- [旧数据仍慢 8 小时] → 用户已明确不回填；在发布说明中注明旧记录保持原值，新记录正确；不做静默修正。
- [混合时区影响超时判断] → 仅 `quiz_jobs.fail_if_timed_out` 受影响，启动清理会先失败旧的 running 任务；变更后任务两端一致。若未来需要严格统一，再单独做数据治理。
- [微信头像只能用户主动选择] → 使用官方 `chooseAvatar`/`nickname` 能力，不尝试静默读取；隐私指引需同步声明。
- [COS 公有读头像可被直接访问] → 头像 URL 本身是公开展示信息；对象键含用户 ID 与随机 UUID，不可枚举；密钥只在服务端。若后续收紧，可改私有桶 + CDN 鉴权。
- [旧头像对象堆积] → 本次不删除，单张 ≤2MB，影响有限；后续可加 COS 生命周期或上传成功后删除旧键。
- [头像上传依赖 COS 配置] → 未配置时明确返回 5001，不影响其他功能；与题目配图共用 `COS_*`，配置一次即可。
- [小程序图片域名] → 头像与题目配图一样需要把 COS/自定义域名加入 `downloadFile` 合法域名（上线检查项）。

## Migration Plan

1. 在 `backend/.env` 增加 `MYSQL_TIME_ZONE=+08:00`（可省略，默认即此值）、`AVATAR_MAX_FILE_MB=2`、`COS_AVATAR_PREFIX=avatars`；同步 `.env.example`。
2. 无需执行 SQL 迁移，不修改 `sql/init_mysql.sql` 结构；重启后端使连接池 `init_command` 生效。
3. 重启后新建一条闯关，确认 `SELECT created_at FROM quiz_sessions ORDER BY id DESC LIMIT 1` 与北京时间一致；旧记录保持不变属预期。
4. 在微信开发者工具上传头像，确认 `users.avatar_url` 为 COS URL、图片可直接访问、个人中心/首页展示正确。
5. 首页确认“今日配图 x/100”与数据库当日用量一致；临时把 `IMAGE_DAILY_LIMIT` 调小验证额度满时开关禁用、文字出题仍可用，验证后恢复 100。
6. 回滚：移除 `MYSQL_TIME_ZONE` 后重启会回到 UTC 写入（已写入的北京时间行不会自动改回）；头像上传可删除路由与前端入口，不影响已保存的 `avatar_url` 展示。无表结构变更需要回滚。
