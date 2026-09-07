-- 会话记忆：把上次路线/日期/人数等槽位保存下来，供对话页显示 chips 与续订追问
USE travel_rag;

CREATE TABLE IF NOT EXISTS session_memories (
    session_id VARCHAR(36) NOT NULL PRIMARY KEY COMMENT '会话ID',
    memory_json TEXT NOT NULL COMMENT '记忆槽位 JSON',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间'
) ENGINE=INNODB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='会话记忆表';
