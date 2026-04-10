import time
import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db
from app.models.order import Order
from app.models.product import Product
from app.schemas.order import OrderCreate, OrderResponse, CallbackRequest
from app.utils.third_party import call_charge_api, call_query_api
from app.utils.sign import verify_sign

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orders", tags=["订单管理"])

# 使用配置中的固定客户编码
FIXED_EUSER_ID = settings.fixed_euser_id


def generate_order_id() -> str:
    """生成32位唯一订单ID"""
    # 使用时间戳 + UUID生成32位订单ID
    timestamp = str(int(time.time() * 1000))[-13:]
    unique_part = uuid.uuid4().hex[:19]
    return timestamp + unique_part


@router.post("/addOrder", response_model=OrderResponse, summary="创建订单")
async def create_order(order: OrderCreate, db: Session = Depends(get_db)):
    """
    创建订单（调用第三方充值接口）

    - 验证商品存在且已上架
    - 调用第三方充值接口
    - 当retCode=2时，调用查询接口确认状态
    - 保存订单到数据库
    """
    # 验证商品存在且已上架
    product = db.query(Product).filter(Product.id == order.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")
    if not product.is_published:
        raise HTTPException(status_code=400, detail="商品未上架")

    # 生成32位唯一订单ID和时间戳
    order_id = generate_order_id()
    timestamp = int(time.time() * 1000)

    # 调用第三方充值接口
    try:
        result = await call_charge_api(
            account_no=order.account_no,
            buy_num=order.quantity,
            euser_id=FIXED_EUSER_ID,
            euser_order_no=order_id,
            product_code=product.third_party_code,
            timestamp=timestamp,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"第三方接口调用失败: {str(e)}")

    # 解析响应
    platform_order_no = result.get("orderNo")
    ret_code = result.get("retCode")
    ret_msg = result.get("retMsg")

    # 当retCode=2时，调用查询接口确认状态
    order_status = "processing"
    card_info = None
    if ret_code == 2 or ret_code == "2":
        # 等待一小段时间后查询
        time.sleep(1)
        query_timestamp = int(time.time() * 1000)
        try:
            query_result = await call_query_api(
                euser_id=FIXED_EUSER_ID,
                euser_order_no=order_id,
                timestamp=query_timestamp,
            )
            order_status = query_result.get("orderStatus", "processing")
            card_info = query_result.get("cardInfo")
        except Exception:
            # 查询失败，保持processing状态
            pass
    elif ret_code == 0 or ret_code == "0":
        order_status = "processing"
    elif ret_code == 1 or ret_code == "1":
        order_status = "fail"

    # 保存订单到数据库
    db_order = Order(
        order_id=order_id,
        euser_id=FIXED_EUSER_ID,
        product_id=order.product_id,
        third_party_code=product.third_party_code,
        quantity=order.quantity,
        account_no=order.account_no,
        request_timestamp=timestamp,
        platform_order_no=platform_order_no,
        ret_code=ret_code,
        ret_msg=ret_msg,
        order_status=order_status,
        card_info=card_info,
    )
    db.add(db_order)
    db.commit()
    db.refresh(db_order)

    return db_order


@router.get("/getOrder", response_model=OrderResponse, summary="查询订单")
async def get_order(
    order_id: str = Query(..., description="订单ID"),
    db: Session = Depends(get_db),
):
    """
    查询订单

    - 验证订单存在
    - 若order_status != processing，直接返回
    - 调用第三方查询接口
    - 更新订单状态和卡密信息
    """
    # 验证订单存在
    db_order = db.query(Order).filter(Order.order_id == order_id).first()
    if not db_order:
        raise HTTPException(status_code=404, detail="订单不存在")

    # 若order_status != processing，直接返回
    if db_order.order_status != "processing":
        return db_order

    # 调用第三方查询接口
    timestamp = int(time.time() * 1000)
    try:
        result = await call_query_api(
            euser_id=FIXED_EUSER_ID,
            euser_order_no=order_id,
            timestamp=timestamp,
        )
        # 打印第三方接口返回日志
        logger.info(f"第三方查询接口返回: {result}")
        print(f"第三方查询接口返回: {result}")
        # 更新订单状态
        if "orderStatus" in result:
            db_order.order_status = result["orderStatus"]
        if "cardInfo" in result:
            db_order.card_info = result["cardInfo"]
        if "retCode" in result:
            db_order.ret_code = result["retCode"]
        if "retMsg" in result:
            db_order.ret_msg = result["retMsg"]
        db.commit()
        db.refresh(db_order)
    except Exception as e:
        # 查询失败，返回现有数据
        pass

    return db_order


@router.delete("/deleteOrder", summary="删除订单")
async def delete_order(
    order_id: str = Query(..., description="订单ID"),
    db: Session = Depends(get_db),
):
    """
    删除订单

    - 验证订单存在
    - 仅当order_status = fail时允许删除
    """
    # 验证订单存在
    db_order = db.query(Order).filter(Order.order_id == order_id).first()
    if not db_order:
        raise HTTPException(status_code=404, detail="订单不存在")

    # 仅当order_status = fail时允许删除
    if db_order.order_status != "fail":
        raise HTTPException(status_code=400, detail="只能删除失败的订单")

    db.delete(db_order)
    db.commit()

    return {"message": "订单删除成功", "order_id": order_id}


@router.post("/callback", summary="订单回调")
async def order_callback(
    callback: CallbackRequest,
    db: Session = Depends(get_db),
):
    """
    订单回调接口（第三方平台调用）

    - 验证签名
    - 查找订单
    - 更新订单状态和卡密信息
    """
    # 1. 验证签名（排除sign字段）
    params = callback.model_dump(exclude={"sign"})
    if not verify_sign(params, callback.sign, settings.apikey):
        raise HTTPException(status_code=400, detail="签名验证失败")

    # 2. 查找订单
    db_order = db.query(Order).filter(
        Order.order_id == callback.euserOrderNo
    ).first()
    if not db_order:
        raise HTTPException(status_code=404, detail="订单不存在")

    # 3. 更新订单信息
    db_order.order_status = callback.orderStatus
    db_order.platform_order_no = callback.orderNo
    if callback.cardInfo:
        db_order.card_info = callback.cardInfo
    if callback.resultMsg:
        db_order.ret_msg = callback.resultMsg
    db_order.ret_code = 0 if callback.orderStatus == "success" else 1

    db.commit()

    # 返回第三方期望的格式
    return "success"