-- 订单表新增支付宝支付信息字段
ALTER TABLE orders
    ADD COLUMN alipay_trade_no VARCHAR(64) NULL COMMENT '支付宝交易号' AFTER pay_status,
    ADD COLUMN alipay_info TEXT NULL COMMENT '支付宝支付信息（JSON）' AFTER alipay_trade_no;
