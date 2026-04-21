-- =====================================================
-- 订单表创建脚本
-- 数据库: ys_third_party
-- =====================================================

CREATE TABLE IF NOT EXISTS `orders` (
    `order_id` VARCHAR(32) PRIMARY KEY COMMENT '订单ID（32位唯一字符串）',
    `euser_id` VARCHAR(50) NOT NULL COMMENT '客户编码（固定值）',
    `product_id` INT NOT NULL COMMENT '商品ID',
    `third_party_code` VARCHAR(100) NOT NULL COMMENT '第三方产品编码',
    `quantity` INT NOT NULL COMMENT '购买数量',
    `total_amount` DECIMAL(10,2) NULL COMMENT '订单总金额（售价×数量）',
    `pay_status` VARCHAR(20) DEFAULT 'pending' COMMENT '支付状态：pending/paid/closed',
    `pay_channel` VARCHAR(20) NULL DEFAULT NULL COMMENT '支付渠道：alipay/wechat，访问支付链接时确定',
    `alipay_trade_no` VARCHAR(64) NULL COMMENT '支付宝交易号',
    `alipay_info` TEXT NULL COMMENT '支付宝支付信息（JSON）',
    `wechat_transaction_id` VARCHAR(32) NULL COMMENT '微信支付交易号',
    `wechat_info` TEXT NULL COMMENT '微信支付信息（JSON）',
    `account_no` VARCHAR(20) NOT NULL COMMENT '充值账号（手机号）',
    `request_timestamp` BIGINT NOT NULL COMMENT '请求时间戳（毫秒）',
    `platform_order_no` VARCHAR(100) NULL COMMENT '平台订单号',
    `ret_code` INT NULL COMMENT '操作状态码（0/1/2）',
    `ret_msg` VARCHAR(255) NULL COMMENT '接单结果描述',
    `order_status` VARCHAR(20) DEFAULT 'pending' COMMENT '订单状态',
    `card_info` TEXT NULL COMMENT '卡密信息',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

    INDEX `idx_product_id` (`product_id`),
    INDEX `idx_order_status` (`order_status`),
    INDEX `idx_created_at` (`created_at`),
    INDEX `idx_account_no` (`account_no`),
    FOREIGN KEY (`product_id`) REFERENCES `products`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='订单表';
