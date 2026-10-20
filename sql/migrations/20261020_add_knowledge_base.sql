-- 迁移：新增个人知识库文档表 knowledge_documents
-- 变更 add-knowledge-base-rag
-- 说明：纯新增表（IF NOT EXISTS，可重复执行），不修改任何既有表；执行一次即可。
-- 回滚：如需撤销，执行文件末尾的 ROLLBACK 语句（会丢弃文档记录；向量与上传文件需另行清理）。

USE `ai_learn`;

CREATE TABLE IF NOT EXISTS knowledge_documents (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '文档ID，自增主键',
    doc_id VARCHAR(64) NOT NULL COMMENT '文档业务ID（后端生成的 doc_xxx，全局唯一）',
    user_id BIGINT UNSIGNED NOT NULL COMMENT '所属用户ID，关联 users.id',
    file_name VARCHAR(255) NOT NULL COMMENT '上传时的原始文件名（仅保留文件名部分）',
    file_ext VARCHAR(16) NOT NULL COMMENT '文件扩展名（pdf/docx/md/txt）',
    file_size BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '文件大小（字节）',
    file_path VARCHAR(1000) NOT NULL DEFAULT '' COMMENT '本地保存路径',
    status VARCHAR(16) NOT NULL DEFAULT 'pending' COMMENT '处理状态：pending=排队中，processing=处理中，ready=已就绪，failed=失败',
    chunk_count INT NOT NULL DEFAULT 0 COMMENT '知识片段数量（建库完成后写入）',
    error_message VARCHAR(500) NULL COMMENT '失败时的可读错误摘要，不存异常堆栈',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后更新时间',
    finished_at DATETIME NULL COMMENT '处理进入终态（ready/failed）的时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_knowledge_documents_doc_id (doc_id),
    KEY idx_knowledge_documents_user_status (user_id, status),
    KEY idx_knowledge_documents_user_created (user_id, created_at),
    CONSTRAINT fk_knowledge_documents_user_id
        FOREIGN KEY (user_id) REFERENCES users (id)
        ON DELETE CASCADE
        ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='个人知识库文档表';

-- ROLLBACK（如需撤销，取消注释执行）：
-- DROP TABLE IF EXISTS knowledge_documents;
