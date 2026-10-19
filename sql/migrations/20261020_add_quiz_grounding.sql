-- 迁移：为 quiz_sessions 增加联网接地出题相关列
-- 变更 ground-quiz-generation-with-search
-- 说明：附加列（可空 / 带默认），向后兼容；执行一次即可。
-- 回滚：如需撤销，执行文件末尾的 ROLLBACK 语句（会丢弃已写入的来源/解读数据）。

USE `ai_learn`;

ALTER TABLE quiz_sessions
    ADD COLUMN interpretation TEXT NULL COMMENT '本次出题所选定的领域/角度解读；主题多义时说明按哪个领域出题，未接地或主题明确时可为空' AFTER questions_json,
    ADD COLUMN sources_json JSON NULL COMMENT '参考来源JSON数组，每项含 title/url/score/kind，取自真实联网检索或网页抽取结果' AFTER interpretation,
    ADD COLUMN grounded TINYINT(1) NOT NULL DEFAULT 0 COMMENT '本次是否成功联网接地出题：1=是，0=否' AFTER sources_json;

-- ROLLBACK（如需撤销，取消注释执行）：
-- ALTER TABLE quiz_sessions
--     DROP COLUMN grounded,
--     DROP COLUMN sources_json,
--     DROP COLUMN interpretation;
