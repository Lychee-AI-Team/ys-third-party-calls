from datetime import datetime, timezone, timedelta
from sqlalchemy import Boolean, Column, DateTime, Integer, Numeric, String
from app.database import Base

# 统一使用北京时间（UTC+8）
_BJ_TZ = timezone(timedelta(hours=8))
bj_now = lambda: datetime.now(_BJ_TZ).replace(tzinfo=None)


class Product(Base):
    """商品模型"""
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment="商品名称")
    brand = Column(String(100), nullable=True, comment="品牌")
    third_party_code = Column(String(100), unique=True, nullable=False, comment="第三方产品编码")
    face_value = Column(Numeric(10, 2), nullable=False, default=0, comment="面值")
    charge_type = Column(Integer, nullable=False, default=1, comment="充值类型：1直充 2卡密")
    category_name = Column(String(100), nullable=True, comment="分类名称")
    display_name = Column(String(200), nullable=True, comment="显示名称")
    selling_price = Column(Numeric(10, 2), nullable=False, default=0, comment="售价")
    is_published = Column(Boolean, default=False, comment="上架状态")
    created_at = Column(DateTime, default=bj_now, comment="创建时间")
    updated_at = Column(DateTime, default=bj_now, onupdate=bj_now, comment="更新时间")
