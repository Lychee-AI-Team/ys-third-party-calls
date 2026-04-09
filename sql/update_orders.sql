-- =====================================================
-- 订单表字段修改
-- 将 user_id 改为 euser_id
-- =====================================================

ALTER TABLE orders CHANGE COLUMN user_id euser_id VARCHAR(50) NOT NULL COMMENT '客户编码（固定值）';