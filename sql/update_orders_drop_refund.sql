-- 删除退款相关字段
ALTER TABLE orders
    DROP COLUMN refund_amount,
    DROP COLUMN refund_trade_no,
    DROP COLUMN out_request_no,
    DROP COLUMN refund_info;
