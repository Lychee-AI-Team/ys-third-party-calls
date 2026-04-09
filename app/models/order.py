from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String, Text, BigInteger, ForeignKey
from app.database import Base


class Order(Base):
    """订单模型"""
    __tablename__ = "orders"

    order_id = Column(String(32), primary_key=True, comment="订单ID（32位唯一字符串）")
    euser_id = Column(String(50), nullable=False, comment="客户编码（固定值）")
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, comment="商品ID")
    third_party_code = Column(String(100), nullable=False, comment="第三方产品编码")
    quantity = Column(Integer, nullable=False, comment="购买数量")
    account_no = Column(String(20), nullable=False, comment="充值账号（手机号）")
    request_timestamp = Column(BigInteger, nullable=False, comment="请求时间戳（毫秒）")
    platform_order_no = Column(String(100), nullable=True, comment="平台订单号")
    ret_code = Column(Integer, nullable=True, comment="操作状态码（0/1/2）")
    ret_msg = Column(String(255), nullable=True, comment="接单结果描述")
    order_status = Column(String(20), default="processing", comment="订单状态")
    card_info = Column(Text, nullable=True, comment="卡密信息")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")