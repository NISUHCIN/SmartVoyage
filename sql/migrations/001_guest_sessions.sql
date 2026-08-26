-- 游客会话落库：允许 chat_sessions.user_id 为空
USE travel_rag;
ALTER TABLE chat_sessions MODIFY user_id INT NULL COMMENT '用户ID（游客为空）';
