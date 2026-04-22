from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, Field


class ProductCreate(BaseModel):
    """创建商品请求模型"""
    name: str = Field(..., max_length=100, description="商品名称")
    brand: Optional[str] = Field(None, max_length=100, description="品牌")
    third_party_code: str = Field(..., max_length=100, description="第三方产品编码")
    face_value: Decimal = Field(0, ge=0, description="面值")
    charge_type: int = Field(1, description="充值类型：1直充 2卡密")
    category_name: Optional[str] = Field(None, max_length=100, description="分类名称")
    display_name: Optional[str] = Field(None, max_length=200, description="显示名称")
    selling_price: Decimal = Field(..., ge=0, description="售价")


class ProductUpdate(BaseModel):
    """更新商品请求模型"""
    name: Optional[str] = Field(None, max_length=100, description="商品名称")
    brand: Optional[str] = Field(None, max_length=100, description="品牌")
    third_party_code: Optional[str] = Field(None, max_length=100, description="第三方产品编码")
    face_value: Optional[Decimal] = Field(None, ge=0, description="面值")
    charge_type: Optional[int] = Field(None, description="充值类型：1直充 2卡密")
    category_name: Optional[str] = Field(None, max_length=100, description="分类名称")
    display_name: Optional[str] = Field(None, max_length=200, description="显示名称")
    selling_price: Optional[Decimal] = Field(None, ge=0, description="售价")


class ProductResponse(BaseModel):
    """商品响应模型"""
    id: int
    name: str
    brand: Optional[str] = None
    third_party_code: str
    face_value: Decimal
    charge_type: int
    category_name: Optional[str] = None
    display_name: Optional[str] = None
    selling_price: Decimal
    is_published: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProductListResponse(BaseModel):
    """商品列表响应模型"""
    total: int = Field(..., description="总数")
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页数量")
    products: List[ProductResponse] = Field(..., description="商品列表")
