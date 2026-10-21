-- 迁移：为 quiz_jobs 增加阶段耗时埋点列
-- 变更：add-home-quiz-mode-toggles
-- 说明：附加可空列，向后兼容；通过 information_schema 判断，可重复执行。
-- 回滚：如需撤销，执行文件末尾的 ROLLBACK 语句（会丢弃已记录的耗时数据）。

USE `ai_learn`;

SET @timings_column_exists = (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'quiz_jobs'
      AND COLUMN_NAME = 'timings_json'
);

SET @timings_ddl = IF(
    @timings_column_exists = 0,
    'ALTER TABLE quiz_jobs ADD COLUMN timings_json JSON NULL COMMENT ''各阶段耗时与调用次数JSON（毫秒），用于定位慢点'' AFTER error_message',
    'SELECT 1'
);

PREPARE timings_stmt FROM @timings_ddl;
EXECUTE timings_stmt;
DEALLOCATE PREPARE timings_stmt;

-- ROLLBACK（如需撤销，取消注释执行）：
-- ALTER TABLE quiz_jobs DROP COLUMN timings_json;
