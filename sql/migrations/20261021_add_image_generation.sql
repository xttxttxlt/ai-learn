-- 迁移：新增每日配图生成用量表
-- 变更：题目配图每人每日额度（默认 100 张）
-- 说明：纯新增表，可重复执行；不修改任何既有表。
-- 回滚：如需撤销，执行文件末尾的 DROP TABLE 语句（会丢弃当日及历史用量）。

USE `ai_learn`;

CREATE TABLE IF NOT EXISTS image_generation_usage (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '用量ID，自增主键',
    user_id BIGINT UNSIGNED NOT NULL COMMENT '所属用户ID，关联 users.id',
    usage_date DATE NOT NULL COMMENT '配额日期（自然日）',
    image_count INT NOT NULL DEFAULT 0 COMMENT '当日已预留或已成功转存的配图张数',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_image_usage_user_date (user_id, usage_date),
    CONSTRAINT fk_image_usage_user_id
        FOREIGN KEY (user_id) REFERENCES users (id)
        ON DELETE CASCADE
        ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='每日配图生成用量表';

-- ROLLBACK（如需撤销，取消注释执行）：
-- DROP TABLE IF EXISTS image_generation_usage;
