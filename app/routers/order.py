import json
import re
import time
import uuid
import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db
from app.models.order import Order
from app.models.product import Product
from app.schemas.order import OrderCreate, OrderResponse, OrderListCreateResponse, CallbackRequest
from app.utils.third_party import call_charge_api, call_query_api
from app.utils.sign import verify_sign
from app.mcp.alipay_client import call_alipay_tool

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orders", tags=["订单管理"])

# 使用配置中的固定客户编码
FIXED_EUSER_ID = settings.fixed_euser_id


def generate_order_id() -> str:
    """生成32位唯一订单ID"""
    timestamp = str(int(time.time() * 1000))[-13:]
    unique_part = uuid.uuid4().hex[:19]
    return timestamp + unique_part


def extract_alipay_info(alipay_result: dict) -> dict:
    """从支付宝返回结果中提取关键信息

    支持多种返回格式：
    - JSON 结构: {"tradeNo": "xxx"}
    - 中文文本-支付: "支付宝交易号: 2026041522001442081435263533"
    - 中文文本-退款: "退款结果: 退款成功, 退款交易: 2026041622001442081440243290"
    - 文本嵌入JSON: "退款结果: {\"tradeNo\":\"xxx\"}"
    - 英文格式: "trade_no=xxx" 或 "trade_no: xxx"
    """
    import re
    info = {}

    # 1. 从 JSON 结构中直接提取
    if "tradeNo" in alipay_result:
        info["trade_no"] = alipay_result["tradeNo"]

    # 2. 从文本中提取
    raw = alipay_result.get("raw_text", "")
    if not raw:
        raw = str(alipay_result)

    if raw and "trade_no" not in info:
        # 先尝试从嵌入的 JSON 中提取（如 "退款结果: {...}"）
        json_match = re.search(r'\{[^}]*"tradeNo"\s*:\s*"(\d+)"', raw)
        if json_match:
            info["trade_no"] = json_match.group(1)
        # 中文格式-退款: "退款交易: 20260416..."
        else:
            match = re.search(r'退款交易[：:]\s*(\d+)', raw)
            if match:
                info["trade_no"] = match.group(1)
            # 中文格式-支付: "支付宝交易号: 20260415..."
            else:
                match = re.search(r'支付宝交易号[：:]\s*(\d+)', raw)
                if match:
                    info["trade_no"] = match.group(1)
                # 英文/JSON 格式
                elif re.search(r'trade_no', raw, re.IGNORECASE):
                    match = re.search(r'trade_no["\s]*[=:]\s*"?(\d+)"?', raw, re.IGNORECASE)
                    if match:
                        info["trade_no"] = match.group(1)

    # 3. 提取交易状态
    if raw:
        match = re.search(r'交易状态[：:]\s*(\w+)', raw)
        if match:
            info["trade_status"] = match.group(1)

    return info


async def trigger_charge(db: Session, db_order: Order, product: Product):
    """支付成功后调用第三方充值接口"""
    try:
        result = await call_charge_api(
            account_no=db_order.account_no,
            buy_num=db_order.quantity,
            euser_id=FIXED_EUSER_ID,
            euser_order_no=db_order.order_id,
            product_code=db_order.third_party_code,
            timestamp=int(time.time() * 1000),
        )
    except Exception as e:
        logger.error(f"第三方充值接口调用失败: {str(e)}")
        db_order.order_status = "fail"
        db_order.ret_msg = f"充值接口调用失败: {str(e)}"
        db_order.ret_code = 1
        db.commit()
        return

    ret_code = result.get("retCode")
    ret_msg = result.get("retMsg")

    # 确定订单状态
    if ret_code == 1 or ret_code == "1":
        order_status = "fail"
    else:
        order_status = "processing"

    db_order.platform_order_no = result.get("orderNo")
    db_order.ret_code = ret_code
    db_order.ret_msg = ret_msg
    db_order.order_status = order_status

    # retCode=2 时查询确认
    if ret_code == 2 or ret_code == "2":
        try:
            query_result = await call_query_api(
                euser_id=FIXED_EUSER_ID,
                euser_order_no=db_order.order_id,
                timestamp=int(time.time() * 1000),
            )
            if "orderStatus" in query_result:
                db_order.order_status = query_result["orderStatus"]
            if "cardInfo" in query_result:
                db_order.card_info = query_result["cardInfo"]
        except Exception:
            pass

    db.commit()


@router.post("/addOrder", response_model=OrderListCreateResponse, summary="创建订单")
async def create_order(order: OrderCreate, db: Session = Depends(get_db)):
    """
    创建订单（先发起支付宝支付，支付成功后自动充值）

    - 验证商品存在且已上架
    - 创建订单（pay_status=pending）
    - 调用支付宝MCP创建支付，返回支付链接
    """
    created_orders = []
    payment_links = []

    try:
        for item in order.items:
            # 验证商品存在且已上架
            product = db.query(Product).filter(Product.id == item.product_id).first()
            if not product:
                raise HTTPException(status_code=404, detail=f"商品不存在: {item.product_id}")
            if not product.is_published:
                raise HTTPException(status_code=400, detail=f"商品未上架: {item.product_id}")

            # 防重复：同一账号+商品+数量已有pending订单则返回已有订单
            existing = db.query(Order).filter(
                Order.account_no == order.account_no,
                Order.product_id == item.product_id,
                Order.quantity == item.quantity,
                Order.pay_status == "pending",
            ).first()
            if existing:
                # 检查pending订单是否超过30分钟（支付链接有效期），超时则删除允许重新创建
                if existing.created_at and existing.created_at < datetime.utcnow() - timedelta(minutes=10):
                    logger.info(f"pending订单已超时，删除旧订单: order_id={existing.order_id}, created_at={existing.created_at}")
                    db.delete(existing)
                    db.flush()
                else:
                    logger.info(f"该账号已有同商品pending订单: order_id={existing.order_id}, product_id={item.product_id}, account_no={order.account_no}")
                    created_orders.append(existing)
                    payment_links.append({"order_id": existing.order_id, "pay_url": f"{settings.base_url}/orders/pay/{existing.order_id}"})
                    continue

            # 生成32位唯一订单ID和时间戳
            order_id = generate_order_id()
            timestamp = int(time.time() * 1000)

            # 计算订单总金额
            total_amount = product.selling_price * item.quantity

            # 保存订单到数据库（仅创建，不调用第三方充值）
            db_order = Order(
                order_id=order_id,
                euser_id=FIXED_EUSER_ID,
                product_id=item.product_id,
                third_party_code=product.third_party_code,
                quantity=item.quantity,
                total_amount=total_amount,
                pay_status="pending",
                account_no=order.account_no,
                request_timestamp=timestamp,
                order_status="pending",
            )
            db.add(db_order)
            created_orders.append(db_order)

            # 调用支付宝MCP创建支付
            try:
                alipay_args = {
                    "outTradeNo": order_id,
                    "totalAmount": float(total_amount),
                    "orderTitle": product.name,
                }
                alipay_result = await call_alipay_tool("create-web-page-alipay-payment", alipay_args)
                # 提取支付宝交易号等信息
                alipay_info = extract_alipay_info(alipay_result)
                if alipay_info.get("trade_no"):
                    db_order.alipay_trade_no = alipay_info["trade_no"]
                db_order.alipay_info = json.dumps(alipay_result, ensure_ascii=False)
                payment_links.append({
                    "order_id": order_id,
                    "pay_url": f"{settings.base_url}/orders/pay/{order_id}",
                })
            except Exception as e:
                logger.error(f"支付宝支付创建失败: {str(e)}")
                # 支付失败，回滚该订单
                db.delete(db_order)
                created_orders.pop()
                raise HTTPException(status_code=500, detail=f"支付宝支付创建失败: {str(e)}")

        db.commit()
        for o in created_orders:
            db.refresh(o)
    except HTTPException:
        db.rollback()
        raise

    return OrderListCreateResponse(
        orders=created_orders,
        total_count=len(created_orders),
    )


@router.get("/getOrder", response_model=OrderResponse, summary="查询订单")
async def get_order(
    order_id: str = Query(..., description="订单ID"),
    db: Session = Depends(get_db),
):
    """
    查询订单

    - 待支付(pay_status=pending)：查询支付宝支付状态，支付成功后自动触发充值
    - 已支付充值中(pay_status=paid, order_status=processing)：查询第三方充值状态
    - 其他状态：直接返回
    """
    db_order = db.query(Order).filter(Order.order_id == order_id).with_for_update().first()
    if not db_order:
        raise HTTPException(status_code=404, detail="订单不存在")

    # 待支付：查询支付宝支付状态
    if db_order.pay_status == "pending":
        try:
            result = await call_alipay_tool("query-alipay-payment", {"outTradeNo": order_id})
            # 存储支付宝查询结果
            alipay_info = extract_alipay_info(result)
            if alipay_info.get("trade_no"):
                db_order.alipay_trade_no = alipay_info["trade_no"]
            db_order.alipay_info = json.dumps(result, ensure_ascii=False)
            raw_text = result.get("raw_text", "")
            if "TRADE_SUCCESS" in raw_text or "支付成功" in raw_text:
                # 再次检查状态，防止并发重复充值
                db.refresh(db_order)
                if db_order.pay_status != "pending":
                    logger.info(f"订单状态已变更，跳过充值: order_id={order_id}, pay_status={db_order.pay_status}")
                else:
                    # 支付成功，更新状态并触发充值
                    db_order.pay_status = "paid"
                    db_order.order_status = "processing"
                    db.commit()
                    db.refresh(db_order)

                    # 触发第三方充值
                    product = db.query(Product).filter(Product.id == db_order.product_id).first()
                    if product:
                        await trigger_charge(db, db_order, product)
                        db.refresh(db_order)
        except Exception as e:
            logger.warning(f"支付宝支付查询失败: {str(e)}")
        return db_order

    # 已支付充值中：查询第三方充值状态
    if db_order.pay_status == "paid" and db_order.order_status == "processing":
        try:
            result = await call_query_api(
                euser_id=FIXED_EUSER_ID,
                euser_order_no=order_id,
                timestamp=int(time.time() * 1000),
            )
            logger.info(f"第三方查询接口返回: {result}")
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
            logger.warning(f"第三方查询接口调用失败: {str(e)}")

    return db_order



def _extract_pay_url(alipay_info_str: str) -> str:
    """从 alipay_info JSON 字符串中提取支付宝支付链接"""
    if not alipay_info_str:
        return ""
    try:
        alipay_data = json.loads(alipay_info_str)
        raw_text = alipay_data.get("raw_text", "")
        match = re.search(r'\[.*?\]\((https://openapi\.alipay\.com[^\)]+)\)', raw_text)
        if match:
            return match.group(1)
    except (json.JSONDecodeError, AttributeError):
        pass
    return ""


@router.get("/pay/{order_id}", summary="支付代理页面")
async def pay_order(order_id: str, db: Session = Depends(get_db)):
    """
    支付代理页面
    - 订单存在且 pending → 302 重定向到支付宝支付链接
    - 订单不存在/已过期/已支付 → 显示"订单已关闭"提示页
    """
    db_order = db.query(Order).filter(Order.order_id == order_id).first()

    if not db_order or db_order.pay_status != "pending":
        return HTMLResponse(content="<!DOCTYPE html>\n<html>\n<head><meta charset=\"utf-8\"><title>订单已关闭</title></head>\n<body style=\"display:flex;justify-content:center;align-items:center;height:100vh;margin:0;font-family:sans-serif;\">\n<div style=\"text-align:center;\">\n<h2 style=\"color:#999;\">订单已关闭</h2>\n<p>该订单已过期或已处理，请重新下单</p>\n</div>\n</body>\n</html>", status_code=200)

    # 检查pending订单是否超过10分钟（支付链接有效期）
    if db_order.created_at and db_order.created_at < datetime.utcnow() - timedelta(minutes=10):
        return HTMLResponse(content="<!DOCTYPE html>\n<html>\n<head><meta charset=\"utf-8\"><title>订单已关闭</title></head>\n<body style=\"display:flex;justify-content:center;align-items:center;height:100vh;margin:0;font-family:sans-serif;\">\n<div style=\"text-align:center;\">\n<h2 style=\"color:#999;\">订单已关闭</h2>\n<p>该订单已超时，请重新下单</p>\n</div>\n</body>\n</html>", status_code=200)

    # 从 alipay_info 中提取支付宝支付链接
    pay_url = _extract_pay_url(db_order.alipay_info)

    if not pay_url:
        # 提取不到链接，返回提示
        return HTMLResponse(content="<!DOCTYPE html>\n<html>\n<head><meta charset=\"utf-8\"><title>支付链接获取失败</title></head>\n<body style=\"display:flex;justify-content:center;align-items:center;height:100vh;margin:0;font-family:sans-serif;\">\n<div style=\"text-align:center;\">\n<h2 style=\"color:#e67e22;\">支付链接获取失败</h2>\n<p>请稍后重试或重新下单</p>\n</div>\n</body>\n</html>", status_code=200)

    return RedirectResponse(url=pay_url, status_code=302)


@router.post("/callback", summary="订单回调")
async def order_callback(
    callback: CallbackRequest,
    db: Session = Depends(get_db),
):
    """
    订单回调接口（第三方充值平台调用）

    - 验证签名
    - 查找订单
    - 更新订单状态和卡密信息
    """
    logger.info(f"收到订单回调请求: {callback.model_dump()}")

    # 1. 验证签名
    params = callback.model_dump(exclude={"sign"})
    if not verify_sign(params, callback.sign, settings.apikey):
        logger.warning(f"签名验证失败, 订单号: {callback.euserOrderNo}")
        raise HTTPException(status_code=400, detail="签名验证失败")

    # 2. 查找订单
    db_order = db.query(Order).filter(
        Order.order_id == callback.euserOrderNo
    ).first()
    if not db_order:
        logger.warning(f"订单不存在: {callback.euserOrderNo}")
        raise HTTPException(status_code=404, detail="订单不存在")

    # 3. 幂等性检查：只有 paid 且 processing 状态才更新
    if db_order.pay_status != "paid" or db_order.order_status != "processing":
        logger.info(f"订单状态不满足更新条件，跳过: {callback.euserOrderNo}, pay_status={db_order.pay_status}, order_status={db_order.order_status}")
        return "success"

    # 4. 更新订单信息
    db_order.order_status = callback.orderStatus
    db_order.platform_order_no = callback.orderNo
    if callback.cardInfo:
        db_order.card_info = callback.cardInfo
    if callback.resultMsg:
        db_order.ret_msg = callback.resultMsg
    db_order.ret_code = 0 if callback.orderStatus == "success" else 1

    db.commit()

    logger.info(f"订单回调处理成功, 订单号: {callback.euserOrderNo}, 状态: {callback.orderStatus}")

    return "success"


@router.post("/callback/alipay", summary="支付宝支付回调")
async def alipay_callback(
    out_trade_no: str = Form(..., description="商户订单号"),
    trade_status: str = Form(..., description="交易状态"),
    trade_no: str = Form(None, description="支付宝交易号"),
    total_amount: str = Form(None, description="交易金额"),
    db: Session = Depends(get_db),
):
    """
    支付宝支付回调（增强安全性）

    安全机制：
    - 收到回调后主动调用支付宝查询接口验证交易真实性
    - 校验实际支付金额与订单金额匹配
    - 行级锁防止并发重复充值
    """
    logger.info(f"[alipay_callback] 收到回调: out_trade_no={out_trade_no}, trade_status={trade_status}, trade_no={trade_no}, total_amount={total_amount}")

    # 1. 行级锁查询订单
    db_order = db.query(Order).filter(Order.order_id == out_trade_no).with_for_update().first()
    if not db_order:
        logger.warning(f"[alipay_callback] 订单不存在: out_trade_no={out_trade_no}")
        return "success"

    # 幂等：已处理过的订单直接返回
    if db_order.pay_status != "pending":
        logger.info(f"[alipay_callback] 订单已处理: out_trade_no={out_trade_no}, pay_status={db_order.pay_status}")
        return "success"

    # 2. 非 TRADE_SUCCESS 直接忽略
    if trade_status != "TRADE_SUCCESS":
        logger.info(f"[alipay_callback] 非成功状态，忽略: out_trade_no={out_trade_no}, trade_status={trade_status}")
        return "success"

    # 3. 校验回调金额（第一层验证）
    if total_amount:
        try:
            actual_amount = float(total_amount)
            expected_amount = float(db_order.total_amount)
            if abs(actual_amount - expected_amount) > 0.01:
                logger.error(f"[alipay_callback] 回调金额不匹配: out_trade_no={out_trade_no}, expected={expected_amount}, actual={actual_amount}")
                return "success"
        except (ValueError, TypeError):
            pass

    # 4. 主动调用支付宝查询接口验证交易真实性（第二层验证）
    try:
        query_result = await call_alipay_tool("query-alipay-payment", {"outTradeNo": out_trade_no})
        raw_text = query_result.get("raw_text", "")
        logger.info(f"[alipay_callback] 支付宝查询结果: out_trade_no={out_trade_no}, raw_text={raw_text}")

        # 验证交易确实成功
        if "TRADE_SUCCESS" not in raw_text and "支付成功" not in raw_text:
            logger.warning(f"[alipay_callback] 支付宝查询未确认支付成功: out_trade_no={out_trade_no}")
            return "success"

        # 验证金额匹配
        amount_match = re.search(r'交易金额[：:]\s*(\d+\.?\d*)', raw_text)
        if amount_match:
            actual_amount = float(amount_match.group(1))
            expected_amount = float(db_order.total_amount)
            if abs(actual_amount - expected_amount) > 0.01:
                logger.error(f"[alipay_callback] 查询金额不匹配: out_trade_no={out_trade_no}, expected={expected_amount}, actual={actual_amount}")
                return "success"

        # 提取并记录支付宝交易号
        alipay_info = extract_alipay_info(query_result)
        if alipay_info.get("trade_no"):
            db_order.alipay_trade_no = alipay_info["trade_no"]
        elif trade_no:
            db_order.alipay_trade_no = trade_no
        db_order.alipay_info = json.dumps(query_result, ensure_ascii=False)

    except Exception as e:
        logger.error(f"[alipay_callback] 支付宝查询失败: out_trade_no={out_trade_no}, error={str(e)}")
        # 查询失败不更新状态，等待下次回调或手动查询
        return "success"

    # 5. 二次状态检查（防止查询期间状态被其他请求修改）
    db.refresh(db_order)
    if db_order.pay_status != "pending":
        logger.info(f"[alipay_callback] 订单状态已变更，跳过: out_trade_no={out_trade_no}, pay_status={db_order.pay_status}")
        return "success"

    # 6. 更新状态并触发充值
    db_order.pay_status = "paid"
    db_order.order_status = "processing"
    db.commit()
    db.refresh(db_order)

    logger.info(f"[alipay_callback] 支付成功，触发充值: out_trade_no={out_trade_no}")

    # 触发第三方充值
    product = db.query(Product).filter(Product.id == db_order.product_id).first()
    if product:
        await trigger_charge(db, db_order, product)

    return "success"
