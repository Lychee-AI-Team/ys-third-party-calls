from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from app.database import Base


class Product(Base):
    """商品模型"""
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment="商品名称")
    third_party_code = Column(String(100), unique=True, nullable=False, comment="第三方产品编码")
    description = Column(Text, nullable=True, comment="商品信息描述")
    is_published = Column(Boolean, default=False, comment="上架状态")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")