-- pay_channel 改为 nullable，创建订单时不设支付渠道，用户访问支付链接时才确定
ALTER TABLE orders MODIFY COLUMN pay_channel VARCHAR(20) NULL DEFAULT NULL COMMENT '支付渠道：alipay/wechat，访问支付链接时确定';
