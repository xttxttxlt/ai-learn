-- 迁移：为 quiz_sessions 增加断点续答进度列
-- 变更：进度存储改为后端持久化（跨设备续答）
-- 说明：附加列（可空 / 带默认），向后兼容；执行一次即可。
-- 回滚：如需撤销，执行文件末尾的 ROLLBACK 语句（会丢弃已保存的答题进度）。

USE `ai_learn`;

ALTER TABLE quiz_sessions
    ADD COLUMN progress_json JSON NULL COMMENT '答题进度JSON数组（未完成时的已答记录），用于断点续答' AFTER grounded,
    ADD COLUMN current_index INT NOT NULL DEFAULT 0 COMMENT '断点续答起始题号（0基）' AFTER progress_json;

-- ROLLBACK（如需撤销，取消注释执行）：
-- ALTER TABLE quiz_sessions
--     DROP COLUMN current_index,
--     DROP COLUMN progress_json;
