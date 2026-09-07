USE travel_rag;

CREATE TABLE IF NOT EXISTS virtual_train_bookings (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    booking_key VARCHAR(64) NOT NULL COMMENT '真实班次+席别+日期的唯一沙箱占用键',
    order_no VARCHAR(36) NOT NULL COMMENT '关联订单号',
    user_id INT NULL COMMENT '用户ID',
    travel_date DATE NOT NULL COMMENT '乘车日期',
    train_no VARCHAR(20) NOT NULL COMMENT '车次',
    seat_type VARCHAR(20) NOT NULL COMMENT '席别',
    quantity INT NOT NULL DEFAULT 1 COMMENT '占用张数',
    status VARCHAR(20) NOT NULL DEFAULT 'confirmed' COMMENT 'confirmed/cancelled',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    UNIQUE KEY uk_booking_order (booking_key, order_no),
    KEY idx_booking_key_status (booking_key, status),
    KEY idx_order_no (order_no)
) ENGINE=INNODB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='真实车次虚拟订票占用表';
