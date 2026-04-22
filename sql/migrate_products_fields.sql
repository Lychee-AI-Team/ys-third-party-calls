-- =====================================================
-- 商品表字段迁移脚本
-- 新增: brand, face_value, charge_type, category_name, display_name
-- 删除: description, cost_price
-- =====================================================

ALTER TABLE products
    ADD COLUMN brand VARCHAR(100) NULL COMMENT '品牌' AFTER name,
    ADD COLUMN face_value DECIMAL(10,2) NOT NULL DEFAULT 0.00 COMMENT '面值' AFTER third_party_code,
    ADD COLUMN charge_type INT NOT NULL DEFAULT 1 COMMENT '充值类型：1直充 2卡密' AFTER face_value,
    ADD COLUMN category_name VARCHAR(100) NULL COMMENT '分类名称' AFTER charge_type,
    ADD COLUMN display_name VARCHAR(200) NULL COMMENT '显示名称' AFTER category_name;

ALTER TABLE products
    DROP COLUMN description,
    DROP COLUMN cost_price;
