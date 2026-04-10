from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class OrderCreate(BaseModel):
    """创建订单请求模型"""
    product_id: int = Field(..., description="商品ID")
    quantity: int = Field(..., gt=0, description="购买数量（必须大于0）")
    account_no: str = Field(..., min_length=11, max_length=11, description="充值账号（手机号）")

    @field_validator('account_no')
    @classmethod
    def validate_phone(cls, v: str) -> str:
        """验证手机号格式"""
        if not v.isdigit():
            raise ValueError('手机号必须为数字')
        if not v.startswith('1'):
            raise ValueError('手机号格式不正确')
        return v


class CallbackRequest(BaseModel):
    """订单回调请求模型"""
    euserOrderNo: str = Field(..., description="客户交易流水号（订单ID）")
    orderNo: str = Field(..., description="平台订单号")
    orderStatus: str = Field(..., description="充值状态：success/fail")
    sign: str = Field(..., description="签名")
    timestamp: str = Field(..., description="请求时间戳")
    cardInfo: Optional[str] = Field(None, description="卡密信息（加密）")
    resultMsg: Optional[str] = Field(None, description="结果描述")


class OrderResponse(BaseModel):
    """订单响应模型"""
    order_id: str
    euser_id: str
    product_id: int
    third_party_code: str
    quantity: int
    account_no: str
    request_timestamp: int
    platform_order_no: Optional[str] = None
    ret_code: Optional[int] = None
    ret_msg: Optional[str] = None
    order_status: str
    card_info: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True