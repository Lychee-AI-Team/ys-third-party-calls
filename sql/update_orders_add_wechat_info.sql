-- 新增微信支付相关字段
ALTER TABLE orders
    ADD COLUMN pay_channel VARCHAR(20) DEFAULT 'alipay' COMMENT '支付渠道：alipay/wechat' AFTER pay_status,
    ADD COLUMN wechat_transaction_id VARCHAR(32) NULL COMMENT '微信支付交易号' AFTER alipay_info,
    ADD COLUMN wechat_info TEXT NULL COMMENT '微信支付信息（JSON）' AFTER wechat_transaction_id;
