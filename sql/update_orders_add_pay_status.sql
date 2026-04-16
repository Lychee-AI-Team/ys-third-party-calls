-- 订单表新增支付状态字段
ALTER TABLE orders ADD COLUMN pay_status VARCHAR(20) DEFAULT 'pending' COMMENT '支付状态：pending/paid/refunded' AFTER total_amount;
