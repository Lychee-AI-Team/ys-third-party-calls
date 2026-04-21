import json
import re
import time
import uuid
import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db
from app.models.order import Order
from app.models.product import Product
from app.schemas.order import OrderCreate, OrderResponse, OrderListCreateResponse, CallbackRequest
from app.utils.third_party import call_charge_api, call_query_api
from app.utils.sign import verify_sign
from app.mcp.alipay_client import call_alipay_tool
from app.mcp.wechat.client import get_wechat_client

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
    创建订单（同时返回微信和支付宝支付链接，用户访问时确定支付方式）

    - 验证商品存在且已上架
    - 创建订单（pay_status=pending，pay_channel 未确定）
    - 返回微信和支付宝两种支付链接
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

            # 防重复：同一账号+商品+数量已有pending且pay_channel未确定（或相同渠道）的订单
            existing = db.query(Order).filter(
                Order.account_no == order.account_no,
                Order.product_id == item.product_id,
                Order.quantity == item.quantity,
                Order.pay_status == "pending",
            ).first()
            if existing:
                if existing.created_at and existing.created_at < datetime.utcnow() - timedelta(minutes=10):
                    logger.info(f"pending订单已超时，删除旧订单: order_id={existing.order_id}")
                    db.delete(existing)
                    db.flush()
                else:
                    logger.info(f"该账号已有同商品pending订单: order_id={existing.order_id}")
                    created_orders.append(existing)
                    payment_links.append({
                        "order_id": existing.order_id,
                        "wxpay_url": f"{settings.base_url}/orders/wxpay/{existing.order_id}",
                        "alipay_url": f"{settings.base_url}/orders/pay/{existing.order_id}",
                    })
                    continue

            # 生成32位唯一订单ID和时间戳
            order_id = generate_order_id()
            timestamp = int(time.time() * 1000)

            # 计算订单总金额
            total_amount = product.selling_price * item.quantity

            # 保存订单（pay_channel 不设，等用户访问支付链接时确定）
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
            payment_links.append({
                "order_id": order_id,
                "wxpay_url": f"{settings.base_url}/orders/wxpay/{order_id}",
                "alipay_url": f"{settings.base_url}/orders/pay/{order_id}",
            })

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

    - 微信待支付(pay_channel=wechat, pay_status=pending)：查询微信支付状态，支付成功后自动触发充值
    - 支付宝待支付(pay_channel=alipay, pay_status=pending)：查询支付宝支付状态，支付成功后自动触发充值
    - 已支付充值中(pay_status=paid, order_status=processing)：查询第三方充值状态
    - 其他状态：直接返回
    """
    db_order = db.query(Order).filter(Order.order_id == order_id).with_for_update().first()
    if not db_order:
        raise HTTPException(status_code=404, detail="订单不存在")

    # 待支付：按支付渠道查询支付状态（pay_channel 未确定则跳过）
    if db_order.pay_status == "pending" and db_order.pay_channel:
        if db_order.pay_channel == "wechat":
            # 微信支付查询
            try:
                wechat_client = get_wechat_client()
                result = await wechat_client.query_order(out_trade_no=order_id)
                if not result.get("error"):
                    trade_state = result.get("trade_state", "")
                    # 存储微信查询结果
                    db_order.wechat_info = json.dumps(result, ensure_ascii=False)

                    if trade_state == "SUCCESS":
                        # 记录微信交易号
                        if result.get("transaction_id"):
                            db_order.wechat_transaction_id = result["transaction_id"]
                        db.refresh(db_order)
                        if db_order.pay_status != "pending":
                            logger.info(f"订单状态已变更，跳过充值: order_id={order_id}, pay_status={db_order.pay_status}")
                        else:
                            # 验证金额
                            amount_data = result.get("amount", {})
                            total_paid = amount_data.get("total", 0)
                            expected_fen = int(float(db_order.total_amount) * 100)
                            if total_paid != expected_fen:
                                logger.error(f"微信支付金额不匹配: order_id={order_id}, expected={expected_fen}, actual={total_paid}")
                            else:
                                db_order.pay_status = "paid"
                                db_order.order_status = "processing"
                                if result.get("transaction_id"):
                                    db_order.wechat_transaction_id = result["transaction_id"]
                                db.commit()
                                db.refresh(db_order)

                                product = db.query(Product).filter(Product.id == db_order.product_id).first()
                                if product:
                                    await trigger_charge(db, db_order, product)
                                    db.refresh(db_order)

                    elif trade_state in ("CLOSED", "REVOKED", "PAYERROR"):
                        logger.info(f"微信订单已关闭/撤销/支付失败: order_id={order_id}, trade_state={trade_state}")
                        db_order.pay_status = "closed"
                        db_order.order_status = "fail"
                        db.commit()
                        db.refresh(db_order)
            except Exception as e:
                logger.warning(f"微信支付查询失败: {str(e)}")
        else:
            # 支付宝查询
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


@router.get("/pay/{order_id}", summary="支付宝支付代理页面")
async def pay_order(order_id: str, db: Session = Depends(get_db)):
    """
    支付宝支付代理页面
    - pay_channel 未确定 → 设为 alipay，调用支付宝创建支付，302 重定向
    - pay_channel=alipay → 提取支付链接，302 重定向
    - pay_channel=wechat → 提示"订单不可采用当前支付方式支付"
    - 订单不存在/已过期/已支付 → 显示"订单已关闭"提示页
    """
    # 行级锁防竞态：防止同时访问 wxpay 和 pay 导致双渠道支付
    db_order = db.query(Order).filter(Order.order_id == order_id).with_for_update().first()

    if not db_order or db_order.pay_status != "pending":
        return HTMLResponse(content=_closed_order_html("订单已关闭", "该订单已过期或已处理，请重新下单"))

    if db_order.created_at and db_order.created_at < datetime.utcnow() - timedelta(minutes=10):
        return HTMLResponse(content=_closed_order_html("订单已关闭", "该订单已超时，请重新下单"))

    # pay_channel 已确定为微信，不允许用支付宝
    if db_order.pay_channel == "wechat":
        return HTMLResponse(content=_closed_order_html("支付方式不匹配", "该订单已选择微信支付，不可采用支付宝支付"))

    # pay_channel 未确定，设为 alipay 并创建支付
    if not db_order.pay_channel:
        db_order.pay_channel = "alipay"
        try:
            product = db.query(Product).filter(Product.id == db_order.product_id).first()
            alipay_args = {
                "outTradeNo": order_id,
                "totalAmount": float(db_order.total_amount),
                "orderTitle": product.name if product else "订单支付",
            }
            alipay_result = await call_alipay_tool("create-web-page-alipay-payment", alipay_args)
            alipay_info = extract_alipay_info(alipay_result)
            if alipay_info.get("trade_no"):
                db_order.alipay_trade_no = alipay_info["trade_no"]
            db_order.alipay_info = json.dumps(alipay_result, ensure_ascii=False)
            db.commit()
        except Exception as e:
            logger.error(f"支付宝支付创建失败: order_id={order_id}, error={str(e)}")
            # 支付API失败，回滚 pay_channel 避免死锁
            db_order.pay_channel = None
            db.commit()
            return HTMLResponse(content=_closed_order_html("支付创建失败", "请稍后重试或重新下单"))

    # 从 alipay_info 中提取支付宝支付链接
    pay_url = _extract_pay_url(db_order.alipay_info)
    if not pay_url:
        return HTMLResponse(content=_closed_order_html("支付链接获取失败", "请稍后重试或重新下单"))

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


@router.post("/callback/wechat", summary="微信支付回调")
async def wechat_callback(request: Request, db: Session = Depends(get_db)):
    """
    微信支付回调

    安全机制：
    - 验签+解密回调数据
    - 行级锁防止并发重复充值
    - 幂等处理
    - 金额校验
    """
    # 1. 读取请求头和请求体
    headers = dict(request.headers)
    body = await request.body()
    body_str = body.decode("utf-8")

    logger.info(f"[wechat_callback] 收到微信支付回调: headers_keys={list(headers.keys())}")

    # 2. 验签+解密
    wechat_client = get_wechat_client()

    # 首次回调时尝试获取平台证书
    if not wechat_client._platform_certs:
        try:
            await wechat_client._fetch_platform_certificates()
        except Exception as e:
            logger.error(f"[wechat_callback] 获取平台证书失败: {e}")

    callback_data = wechat_client.verify_and_decrypt_callback(headers, body_str)
    if callback_data is None:
        logger.error("[wechat_callback] 验签或解密失败")
        return JSONResponse(
            status_code=400,
            content={"code": "FAIL", "message": "验签失败"},
        )

    logger.info(f"[wechat_callback] 解密成功: out_trade_no={callback_data.get('out_trade_no')}, trade_state={callback_data.get('trade_state')}")

    # 3. 行级锁查询订单
    out_trade_no = callback_data.get("out_trade_no", "")
    db_order = db.query(Order).filter(Order.order_id == out_trade_no).with_for_update().first()
    if not db_order:
        logger.warning(f"[wechat_callback] 订单不存在: out_trade_no={out_trade_no}")
        return JSONResponse(content={"code": "SUCCESS", "message": "成功"})

    # 4. 幂等检查
    if db_order.pay_status != "pending":
        logger.info(f"[wechat_callback] 订单已处理: out_trade_no={out_trade_no}, pay_status={db_order.pay_status}")
        return JSONResponse(content={"code": "SUCCESS", "message": "成功"})

    # 5. 验证金额匹配
    trade_state = callback_data.get("trade_state", "")
    if trade_state != "SUCCESS":
        logger.info(f"[wechat_callback] 非成功状态: out_trade_no={out_trade_no}, trade_state={trade_state}")
        if trade_state in ("CLOSED", "REVOKED", "PAYERROR"):
            db_order.pay_status = "closed"
            db_order.order_status = "fail"
            db.commit()
        return JSONResponse(content={"code": "SUCCESS", "message": "成功"})

    amount_data = callback_data.get("amount", {})
    total_paid = amount_data.get("total", 0)
    expected_fen = int(float(db_order.total_amount) * 100)
    if total_paid != expected_fen:
        logger.error(f"[wechat_callback] 金额不匹配: out_trade_no={out_trade_no}, expected={expected_fen}, actual={total_paid}")
        return JSONResponse(content={"code": "SUCCESS", "message": "成功"})

    # 6. 记录微信交易号
    transaction_id = callback_data.get("transaction_id", "")
    if transaction_id:
        db_order.wechat_transaction_id = transaction_id
    db_order.wechat_info = json.dumps(callback_data, ensure_ascii=False)

    # 7. 二次状态检查
    db.refresh(db_order)
    if db_order.pay_status != "pending":
        logger.info(f"[wechat_callback] 订单状态已变更，跳过: out_trade_no={out_trade_no}, pay_status={db_order.pay_status}")
        return JSONResponse(content={"code": "SUCCESS", "message": "成功"})

    # 8. 更新状态并触发充值
    db_order.pay_status = "paid"
    db_order.order_status = "processing"
    db.commit()
    db.refresh(db_order)

    logger.info(f"[wechat_callback] 微信支付成功，触发充值: out_trade_no={out_trade_no}")

    product = db.query(Product).filter(Product.id == db_order.product_id).first()
    if product:
        await trigger_charge(db, db_order, product)

    return JSONResponse(content={"code": "SUCCESS", "message": "成功"})


@router.get("/wxpay/{order_id}", summary="微信支付二维码页面")
async def wxpay_qrcode(order_id: str, db: Session = Depends(get_db)):
    """
    微信支付二维码展示页面
    - pay_channel 未确定 → 设为 wechat，调用微信 Native 下单，展示二维码
    - pay_channel=wechat → 展示二维码
    - pay_channel=alipay → 提示"订单不可采用当前支付方式支付"
    - 订单不存在/已过期/已支付 → 显示提示页
    """
    # 行级锁防竞态：防止同时访问 wxpay 和 pay 导致双渠道支付
    db_order = db.query(Order).filter(Order.order_id == order_id).with_for_update().first()

    if not db_order or db_order.pay_status != "pending":
        return HTMLResponse(content=_closed_order_html("订单已关闭", "该订单已过期或已处理，请重新下单"))

    if db_order.created_at and db_order.created_at < datetime.utcnow() - timedelta(minutes=10):
        return HTMLResponse(content=_closed_order_html("订单已关闭", "该订单已超时，请重新下单"))

    # pay_channel 已确定为支付宝，不允许用微信
    if db_order.pay_channel == "alipay":
        return HTMLResponse(content=_closed_order_html("支付方式不匹配", "该订单已选择支付宝支付，不可采用微信支付"))

    # pay_channel 未确定，设为 wechat 并创建微信 Native 下单
    if not db_order.pay_channel:
        db_order.pay_channel = "wechat"
        try:
            total_fen = int(float(db_order.total_amount) * 100)
            wechat_client = get_wechat_client()
            wechat_result = await wechat_client.create_native_order(
                out_trade_no=order_id,
                description=db_order.third_party_code,
                total=total_fen,
            )
            if wechat_result.get("error"):
                logger.error(f"微信支付下单失败: order_id={order_id}, result={wechat_result}")
                # 支付API失败，回滚 pay_channel 避免死锁
                db_order.pay_channel = None
                db.commit()
                return HTMLResponse(content=_closed_order_html("支付创建失败", "请稍后重试或重新下单"))
            code_url = wechat_result.get("code_url", "")
            db_order.wechat_info = json.dumps({"code_url": code_url}, ensure_ascii=False)
            db.commit()
        except Exception as e:
            logger.error(f"微信支付下单异常: order_id={order_id}, error={str(e)}")
            # 支付API失败，回滚 pay_channel 避免死锁
            db_order.pay_channel = None
            db.commit()
            return HTMLResponse(content=_closed_order_html("支付创建失败", "请稍后重试或重新下单"))
            return HTMLResponse(content=_closed_order_html("支付创建失败", "请稍后重试或重新下单"))

    # 从 wechat_info 中提取 code_url
    code_url = ""
    if db_order.wechat_info:
        try:
            wechat_data = json.loads(db_order.wechat_info)
            code_url = wechat_data.get("code_url", "")
        except (json.JSONDecodeError, AttributeError):
            pass

    if not code_url:
        return HTMLResponse(content=_closed_order_html("支付链接获取失败", "请稍后重试或重新下单"))

    # 返回二维码展示页面
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>微信支付</title>
    <script src="https://cdn.jsdelivr.net/npm/qrcodejs@1.0.0/qrcode.min.js"></script>
</head>
<body style="display:flex;justify-content:center;align-items:center;min-height:100vh;margin:0;font-family:sans-serif;background:#f5f5f5;">
<div style="text-align:center;background:#fff;padding:40px;border-radius:12px;box-shadow:0 2px 12px rgba(0,0,0,0.1);">
    <h3 style="color:#333;margin-bottom:8px;">微信支付</h3>
    <p style="color:#666;font-size:14px;">订单金额：¥{float(db_order.total_amount):.2f}</p>
    <div id="qrcode" style="margin:20px auto;width:200px;height:200px;"></div>
    <p style="color:#999;font-size:12px;">请使用微信扫码支付</p>
</div>
<script>
new QRCode(document.getElementById("qrcode"), {{
    text: "{code_url}",
    width: 200,
    height: 200,
    colorDark: "#000000",
    colorLight: "#ffffff",
    correctLevel: QRCode.CorrectLevel.M
}});
</script>
</body>
</html>"""
    return HTMLResponse(content=html)


def _closed_order_html(title: str, message: str) -> str:
    """生成订单关闭提示页 HTML"""
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>{title}</title></head>
<body style="display:flex;justify-content:center;align-items:center;height:100vh;margin:0;font-family:sans-serif;">
<div style="text-align:center;">
<h2 style="color:#999;">{title}</h2>
<p>{message}</p>
</div>
</body>
</html>"""
