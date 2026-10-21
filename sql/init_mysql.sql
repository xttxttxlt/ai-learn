CREATE DATABASE IF NOT EXISTS `ai_learn`
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

USE `ai_learn`;

CREATE TABLE IF NOT EXISTS users (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '用户ID，自增主键',
    openid VARCHAR(64) NOT NULL COMMENT '微信openid，用户在本小程序下的唯一标识',
    nickname VARCHAR(100) NOT NULL DEFAULT '学习者' COMMENT '用户昵称',
    avatar_url VARCHAR(500) NOT NULL DEFAULT '' COMMENT '用户头像URL',
    total_coins INT NOT NULL DEFAULT 0 COMMENT '总金币数（答对题目即时累加；原“总经验”字段，现统一为金币）',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_users_openid (openid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户表';

CREATE TABLE IF NOT EXISTS quiz_sessions (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '会话ID，自增主键',
    quiz_id VARCHAR(64) NOT NULL COMMENT '题库业务ID（后端生成的 quiz_xxx，全局唯一）',
    user_id BIGINT UNSIGNED NULL COMMENT '所属用户ID，关联 users.id；未登录时可为空',
    title VARCHAR(255) NOT NULL COMMENT '题库标题',
    summary TEXT NULL COMMENT '题库主题摘要',
    user_input TEXT NULL COMMENT '用户发起出题的原始输入内容',
    questions_json JSON NOT NULL COMMENT '题目列表JSON，含题型/题干/选项/正确答案/解析/知识点/难度',
    interpretation TEXT NULL COMMENT '本次出题所选定的领域/角度解读；主题多义时说明按哪个领域出题，未接地或主题明确时可为空',
    sources_json JSON NULL COMMENT '参考来源JSON数组，每项含 title/url/score/kind，取自真实联网检索或网页抽取结果',
    grounded TINYINT NOT NULL DEFAULT 0 COMMENT '本次是否成功联网接地出题：1=是，0=否',
    progress_json JSON NULL COMMENT '答题进度JSON数组（未完成时的已答记录），用于断点续答',
    current_index INT NOT NULL DEFAULT 0 COMMENT '断点续答起始题号（0基）',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_quiz_sessions_quiz_id (quiz_id),
    KEY idx_quiz_sessions_user_id (user_id),
    KEY idx_quiz_sessions_created_at (created_at),
    CONSTRAINT fk_quiz_sessions_user_id
        FOREIGN KEY (user_id) REFERENCES users (id)
        ON DELETE SET NULL
        ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='题库会话表';

CREATE TABLE IF NOT EXISTS answer_records (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '记录ID，自增主键',
    quiz_id VARCHAR(64) NOT NULL COMMENT '关联题库ID，对应 quiz_sessions.quiz_id',
    user_id BIGINT UNSIGNED NULL COMMENT '所属用户ID，关联 users.id',
    records_json JSON NOT NULL COMMENT '答题明细JSON，逐题记录所选答案、是否正确、答题用时',
    total_questions INT NOT NULL COMMENT '本局题目总数',
    correct_count INT NOT NULL COMMENT '本局答对题目数',
    accuracy DECIMAL(5, 2) NOT NULL COMMENT '正确率，百分比取值 0.00-100.00',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_answer_records_quiz_id (quiz_id),
    KEY idx_answer_records_user_id (user_id),
    KEY idx_answer_records_created_at (created_at),
    CONSTRAINT fk_answer_records_user_id
        FOREIGN KEY (user_id) REFERENCES users (id)
        ON DELETE SET NULL
        ON UPDATE CASCADE,
    CONSTRAINT fk_answer_records_quiz_id
        FOREIGN KEY (quiz_id) REFERENCES quiz_sessions (quiz_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='答题记录表';

CREATE TABLE IF NOT EXISTS reports (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '报告ID，自增主键',
    quiz_id VARCHAR(64) NOT NULL COMMENT '关联题库ID，对应 quiz_sessions.quiz_id',
    user_id BIGINT UNSIGNED NULL COMMENT '所属用户ID，关联 users.id',
    report_json JSON NOT NULL COMMENT '复盘报告JSON，含正确率/掌握点/薄弱点/三句总结/复习建议/分享金句',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_reports_quiz_id (quiz_id),
    KEY idx_reports_user_id (user_id),
    KEY idx_reports_created_at (created_at),
    CONSTRAINT fk_reports_user_id
        FOREIGN KEY (user_id) REFERENCES users (id)
        ON DELETE SET NULL
        ON UPDATE CASCADE,
    CONSTRAINT fk_reports_quiz_id
        FOREIGN KEY (quiz_id) REFERENCES quiz_sessions (quiz_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='复盘报告表';

CREATE TABLE IF NOT EXISTS quiz_jobs (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '任务ID，自增主键',
    job_id VARCHAR(64) NOT NULL COMMENT '任务业务ID（后端生成的 job_xxx，全局唯一）',
    user_id BIGINT UNSIGNED NOT NULL COMMENT '所属用户ID，关联 users.id',
    request_id VARCHAR(64) NOT NULL COMMENT '客户端幂等请求ID，同一用户内唯一',
    status VARCHAR(16) NOT NULL DEFAULT 'pending' COMMENT '任务状态：pending=待执行，running=生成中，completed=已完成，failed=失败',
    params_json JSON NOT NULL COMMENT '出题参数JSON，含 user_input/question_count/difficulty/use_web_search/use_knowledge_base/document_id/generate_images',
    result_json JSON NULL COMMENT '完成后的题库JSON，含题目、接地标记与参考来源',
    error_message VARCHAR(500) NULL COMMENT '失败时的可读错误摘要，不存异常堆栈',
    timings_json JSON NULL COMMENT '各阶段耗时与调用次数JSON（毫秒），用于定位慢点',
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
