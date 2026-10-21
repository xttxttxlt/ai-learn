# Tasks

## 1. 北京时间基础与配置

- [x] 1.1 先补测试再实现：新增 `backend/tests/test_time_utils.py`，验证固定 UTC 时刻下 `beijing_now()/beijing_today()` 的北京时间与跨日行为（UTC 16:00 = 北京次日 00:00）；实现 `app/utils/time_utils.py`（固定 `+08:00`，不依赖 tzdata），运行 `pytest -q tests/test_time_utils.py`
- [x] 1.2 先补测试再实现：在 `tests/test_db_init.py` 断言 `_run_schema_init` 与 `init_db` 都向连接传入 `init_command="SET time_zone = '<MYSQL_TIME_ZONE>'"`，默认 `+08:00` 且可被环境变量覆盖；在 `app/core/config.py` 增加 `mysql_time_zone`，在 `app/core/db.py` 的建表连接与连接池接入 `init_command`，运行 `pytest -q tests/test_db_init.py`
- [x] 1.3 先补测试再实现：把 `app/services/image_generation_service.py` 的 `date.today()` 改为 `beijing_today()`、`app/services/knowledge_base_service.py` 的裸 `datetime.now()` 改为 `beijing_now()`；在既有测试中断言未传 `today` 时使用北京时间，运行 `pytest -q tests/test_image_generation_service.py tests/test_knowledge_base_service.py`
- [x] 1.4 在 `backend/.env.example` 增加 `MYSQL_TIME_ZONE=+08:00`（含“旧数据不回填”说明），确认 `backend/.env` 可覆盖且未提交；检查 `git diff` 只出现配置与代码改动，无 SQL 表结构变更

## 2. 头像上传与 COS 转存（后端）

- [x] 2.1 先补测试再实现：在 `app/core/config.py` 增加 `avatar_max_file_mb=2`、`cos_avatar_prefix="avatars"`、`avatar_max_file_bytes` 与 `cos_ready`（COS 四项必填），并让 `image_generation_ready` 复用 `cos_ready`；测试配置齐全/缺项与既有配图就绪判断不回归，运行 `pytest -q tests/test_image_generation_config.py tests/test_knowledge_base_config.py`
- [x] 2.2 先补测试再实现：`app/services/cos_storage_service.py` 增加通用 `upload_bytes(data, key, settings, content_type)`、`build_avatar_object_key(user_id, ext, prefix, now)`（`avatars/{user_id}/{YYYYMMDD}/{uuid}.{ext}`），保留 `upload_image` 的 PNG 行为；测试上传参数含 `ACL=public-read`、URL 拼接、对象键格式与上传异常返回空，运行 `pytest -q tests/test_avatar_service.py`（COS 相关用例）
- [x] 2.3 先补测试再实现：新增 `app/services/avatar_service.py`，按魔数识别 JPEG/PNG/WebP，拒绝空文件、GIF 等非法格式与超过 `AVATAR_MAX_FILE_MB` 的文件；上传成功后更新 `users.avatar_url`，上传/更新失败时保留旧头像；测试合法三种格式、非法格式、超限、COS 未配置、COS 失败、数据库失败六类路径，运行 `pytest -q tests/test_avatar_service.py`
- [x] 2.4 先补测试再实现：在 `app/api/v1/routes/user.py` 增加 `POST /api/v1/user/avatar`（multipart `file`，已登录），成功返回更新后的 `ProfileOut`，非法格式返回 4000、COS 不可用返回 5001；测试未登录 4010、成功响应含新 `avatar_url`、错误码与旧头像保留，运行 `pytest -q tests/test_user_api.py`

## 3. 每日配图额度接口（后端）

- [x] 3.1 先补测试再实现：`app/models/user.py` 增加 `ImageQuotaOut`（`usage_date/used/limit/remaining/available`）并挂到 `ProfileOut.image_quota`；`user_service.get_profile` 用 `beijing_today()` 读取 `image_usage_repository.get_count`，计算 `remaining=max(0, limit-used)`；测试已用 35/上限 100 返回 `35/100/65`，运行 `pytest -q tests/test_user_api.py`
- [x] 3.2 先补测试再实现：配额查询抛异常时 `available=false`、`used=0`、`remaining=limit`，档案其他字段仍正常返回；测试 FakeDB 抛错场景并确认接口 `code=0`，运行 `pytest -q tests/test_user_api.py`
- [x] 3.3 验证额度日期口径：用 monkeypatch 固定 `beijing_today()` 后请求档案，断言查询参数中的 `usage_date` 为北京时间日期而非 UTC 日期；运行 `pytest -q tests/test_user_api.py tests/test_image_usage_repository.py`

## 4. 前端头像与昵称

- [x] 4.1 扩展 `src/types/index.ts`（`ImageQuota`、`UserProfile.image_quota`）与 `src/services/api.ts`（`uploadAvatar(filePath, fileName)` 走 multipart `/api/v1/user/avatar`）；运行 `npm run build:weapp` 确认类型与构建通过
- [x] 4.2 新增 `src/components/UserAvatar/index.tsx` / `index.scss`：有 `avatar_url` 时展示 `Image mode="aspectFill"`，为空或加载失败回退昵称首字，`src` 变化时重置失败状态；个人中心与首页复用，构建后在 H5 预览确认两种状态
- [x] 4.3 个人中心头像改为 `<Button openType="chooseAvatar" onChooseAvatar>`，选图后调用 `uploadAvatar` 并用返回的 `ProfileOut` 更新页面与 `setCachedUser`；上传中展示 loading，失败 toast 且保留旧头像；构建后在微信开发者工具验证选择微信头像并落库
- [x] 4.4 个人中心昵称改为内联编辑：点击“修改”渲染 `<Input type="nickname" maxLength={20}>` 与保存/取消，保存调用现有 `updateProfile({nickname})`；构建后验证键盘昵称提示、空值与超长校验、保存后首页问候语同步
- [x] 4.5 非微信环境头像入口：`process.env.TARO_ENV !== 'weapp'` 时点击头像调用 `Taro.chooseImage({count: 1})` 并复用同一上传流程；运行 `npm run build:h5` 并人工确认相册选择可用
- [x] 4.6 首页问候区改用 `UserAvatar` 展示真实头像，未设置时保持首字占位且尺寸不变；构建后对比设置头像前后布局，确认不跳动

## 5. 前端配图额度展示与禁用

- [x] 5.1 首页读取 `profile.image_quota`：展示“今日配图 {used}/{limit}”；`available=false` 展示“今日配图 暂不可用”；`remaining<=0` 展示额度已用完并 `disabled` 配图 `Switch`，但“开始生成题目”保持可用；构建后人工确认三种状态
- [x] 5.2 额度满时把 `withImages` 置 false，提交任务时 `generate_images` 为 false；任务 completed 时非阻塞刷新一次 `getProfile()`，`useDidShow` 继续负责回页刷新；构建后确认纯文字出题仍可创建任务
- [x] 5.3 临时把 `IMAGE_DAILY_LIMIT` 调为 0 或把当日 `image_generation_usage.image_count` 改为上限，验证首页显示 `100/100`、开关置灰、文字出题成功；验证后恢复配置/数据

## 6. 集成验证与回归

- [x] 6.1 运行后端全量回归 `cd backend && .venv/Scripts/python.exe -m pytest -q`，确认登录、出题任务、答题、报告、金币、历史、知识库、题目配图全部通过
- [x] 6.2 运行 `cd frontend && npm run build:weapp` 与 `npm run build:h5`，确认两个平台构建成功且无 `src/` 类型错误
- [x] 6.3 真实冒烟：上传头像后确认 `users.avatar_url` 为 COS URL 且可直接访问，个人中心与首页展示正确；新建一条闯关，确认 `created_at` 为北京时间且旧记录保持原值
- [x] 6.4 真实冒烟：从首页发起 5 题配图任务，确认任务前后 `image_quota` 的 `used` 增加；确认额度不足时仍只生成剩余张数，主流程不受影响
- [x] 6.5 在微信开发者工具走通“改头像 → 改昵称 → 首页额度展示 → 纯文字出题 → 配图出题 → 答题 → 报告 → 历史”全流程，确认无回归

## Workflow follow-up

- 实现与验证完成后运行 `openspec validate add-avatar-image-quota-and-timezone --strict`，确认规格、设计与任务一致。
- 经人工评审后再执行 `/opsx:archive` 归档本变更并同步主规格。
- 上线检查：在小程序后台隐私保护指引声明“收集你的昵称、头像”，并把 COS/自定义域名加入 `downloadFile` 合法域名。
