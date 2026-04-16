-- 订单表新增退款信息字段
ALTER TABLE orders
    ADD COLUMN refund_amount DECIMAL(10,2) NULL COMMENT '退款金额' AFTER alipay_info,
    ADD COLUMN refund_trade_no VARCHAR(64) NULL COMMENT '退款交易号' AFTER refund_amount,
    ADD COLUMN refund_reason VARCHAR(255) NULL COMMENT '退款原因' AFTER refund_trade_no,
    ADD COLUMN out_request_no VARCHAR(64) NULL COMMENT '退款请求号' AFTER refund_reason,
    ADD COLUMN refund_info TEXT NULL COMMENT '退款返回信息（JSON）' AFTER out_request_no;
