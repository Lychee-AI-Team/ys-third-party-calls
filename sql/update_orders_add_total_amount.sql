-- 订单表新增总金额字段
ALTER TABLE orders
    ADD COLUMN total_amount DECIMAL(10,2) NULL COMMENT '订单总金额（售价×数量）' AFTER quantity;
