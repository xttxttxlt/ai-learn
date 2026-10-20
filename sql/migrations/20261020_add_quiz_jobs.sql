-- 迁移：新增异步出题任务表 quiz_jobs
-- 变更 add-async-quiz-generation
-- 说明：纯新增表（IF NOT EXISTS，可重复执行），不影响既有表结构；执行一次即可。
-- 回滚：如需撤销，执行文件末尾的 ROLLBACK 语句（会丢弃进行中与已完成的任务记录）。

USE `ai_learn`;

CREATE TABLE IF NOT EXISTS quiz_jobs (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '任务ID，自增主键',
    job_id VARCHAR(64) NOT NULL COMMENT '任务业务ID（后端生成的 job_xxx，全局唯一）',
    user_id BIGINT UNSIGNED NOT NULL COMMENT '所属用户ID，关联 users.id',
    request_id VARCHAR(64) NOT NULL COMMENT '客户端幂等请求ID，同一用户内唯一',
    status VARCHAR(16) NOT NULL DEFAULT 'pending' COMMENT '任务状态：pending=待执行，running=生成中，completed=已完成，failed=失败',
    params_json JSON NOT NULL COMMENT '出题参数JSON，含 user_input/question_count/difficulty',
    result_json JSON NULL COMMENT '完成后的题库JSON，含题目、接地标记与参考来源',
    error_message VARCHAR(500) NULL COMMENT '失败时的可读错误摘要，不存异常堆栈',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后更新时间',
    finished_at DATETIME NULL COMMENT '任务进入终态（completed/failed）的时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_quiz_jobs_job_id (job_id),
    UNIQUE KEY uk_quiz_jobs_user_request (user_id, request_id),
    KEY idx_quiz_jobs_status_created (status, created_at),
    CONSTRAINT fk_quiz_jobs_user_id
        FOREIGN KEY (user_id) REFERENCES users (id)
        ON DELETE CASCADE
        ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='出题任务表';

-- ROLLBACK（如需撤销，取消注释执行）：
-- DROP TABLE IF EXISTS quiz_jobs;
