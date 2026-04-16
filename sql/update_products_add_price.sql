-- 商品表新增价格字段
ALTER TABLE products
    ADD COLUMN cost_price DECIMAL(10,2) NOT NULL DEFAULT 0.00 COMMENT '成本价' AFTER description,
    ADD COLUMN selling_price DECIMAL(10,2) NOT NULL DEFAULT 0.00 COMMENT '售价' AFTER cost_price;
