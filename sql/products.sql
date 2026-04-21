-- =====================================================
-- 商品表创建脚本
-- 数据库: ys_third_party
-- =====================================================

CREATE TABLE IF NOT EXISTS `products` (
    `id` INT AUTO_INCREMENT PRIMARY KEY COMMENT '商品ID',
    `name` VARCHAR(100) NOT NULL COMMENT '商品名称',
    `third_party_code` VARCHAR(100) NOT NULL COMMENT '第三方产品编码',
    `description` TEXT DEFAULT NULL COMMENT '商品信息描述',
    `cost_price` DECIMAL(10,2) NOT NULL DEFAULT 0.00 COMMENT '成本价',
    `selling_price` DECIMAL(10,2) NOT NULL DEFAULT 0.00 COMMENT '售价',
    `is_published` BOOLEAN DEFAULT FALSE COMMENT '上架状态',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

    UNIQUE KEY `uk_third_party_code` (`third_party_code`),
    INDEX `idx_name` (`name`),
    INDEX `idx_is_published` (`is_published`),
    INDEX `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='商品表';
