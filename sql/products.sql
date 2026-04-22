-- =====================================================
-- 商品表创建脚本
-- 数据库: ys_third_party
-- =====================================================

CREATE TABLE IF NOT EXISTS `products` (
    `id` INT AUTO_INCREMENT PRIMARY KEY COMMENT '商品ID',
    `name` VARCHAR(100) NOT NULL COMMENT '商品名称',
    `brand` VARCHAR(100) DEFAULT NULL COMMENT '品牌',
    `third_party_code` VARCHAR(100) NOT NULL COMMENT '第三方产品编码',
    `face_value` DECIMAL(10,2) NOT NULL DEFAULT 0.00 COMMENT '面值',
    `charge_type` INT NOT NULL DEFAULT 1 COMMENT '充值类型：1直充 2卡密',
    `category_name` VARCHAR(100) DEFAULT NULL COMMENT '分类名称',
    `display_name` VARCHAR(200) DEFAULT NULL COMMENT '显示名称',
    `selling_price` DECIMAL(10,2) NOT NULL DEFAULT 0.00 COMMENT '售价',
    `is_published` BOOLEAN DEFAULT FALSE COMMENT '上架状态',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

    UNIQUE KEY `uk_third_party_code` (`third_party_code`),
    INDEX `idx_name` (`name`),
    INDEX `idx_brand` (`brand`),
    INDEX `idx_category_name` (`category_name`),
    INDEX `idx_is_published` (`is_published`),
    INDEX `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='商品表';
