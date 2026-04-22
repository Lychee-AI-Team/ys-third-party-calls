"""MCP Tools 定义（装饰器风格）

对外实例（public）：查询商品、查询订单、创建订单 — product_list, product_get, order_get, order_create
内部实例（internal）：全部工具 — 包含商品CRUD等写入操作
"""
import json
import logging
import time
import uuid
from datetime import datetime, timedelta
from fastmcp import FastMCP
from app.database import SessionLocal
from app.models.product import Product
from app.models.order import Order
from app.utils.third_party import call_charge_api, call_query_api
from app.mcp.alipay_client import call_alipay_tool
from app.mcp.wechat.client import get_wechat_client
from app.config import settings

logger = logging.getLogger(__name__)


# ==================== 辅助函数 ====================

def _extract_alipay_info(alipay_result: dict) -> dict:
    """从支付宝返回结果中提取关键信息"""
    import re
    info = {}

    if "tradeNo" in alipay_result:
        info["trade_no"] = alipay_result["tradeNo"]

    raw = alipay_result.get("raw_text", "")
    if not raw:
        raw = str(alipay_result)

    if raw and "trade_no" not in info:
        json_match = re.search(r'\{[^}]*"tradeNo"\s*:\s*"(\d+)"', raw)
        if json_match:
            info["trade_no"] = json_match.group(1)
        else:
            match = re.search(r'退款交易[：:]\s*(\d+)', raw)
            if match:
                info["trade_no"] = match.group(1)
            else:
                match = re.search(r'支付宝交易号[：:]\s*(\d+)', raw)
                if match:
                    info["trade_no"] = match.group(1)
                elif re.search(r'trade_no', raw, re.IGNORECASE):
                    match = re.search(r'trade_no["\s]*[=:]\s*"?(\d+)"?', raw, re.IGNORECASE)
                    if match:
                        info["trade_no"] = match.group(1)

    if raw:
        match = re.search(r'交易状态[：:]\s*(\w+)', raw)
        if match:
            info["trade_status"] = match.group(1)

    return info


async def _trigger_charge(db, db_order: Order, product: Product):
    """支付成功后调用第三方充值接口（内部辅助函数）"""
    try:
        result = await call_charge_api(
            account_no=db_order.account_no,
            buy_num=db_order.quantity,
            euser_id=settings.fixed_euser_id,
            euser_order_no=db_order.order_id,
            product_code=product.third_party_code,
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

    if ret_code == 1 or ret_code == "1":
        order_status = "fail"
    else:
        order_status = "processing"

    db_order.platform_order_no = result.get("orderNo")
    db_order.ret_code = ret_code
    db_order.ret_msg = ret_msg
    db_order.order_status = order_status

    if ret_code == 2 or ret_code == "2":
        try:
            query_result = await call_query_api(
                euser_id=settings.fixed_euser_id,
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


# ==================== 对外工具（只读）====================

def register_public_tools(mcp: FastMCP):
    """注册对外 MCP Tools（查询商品、查询订单、创建订单）"""

    @mcp.tool()
    def product_list(
        page: int = 1,
        page_size: int = 10,
        keyword: str = None,
    ) -> dict:
        """查询商品列表（仅上架商品）

        Args:
            page: 页码（默认1）
            page_size: 每页数量（默认10）
            keyword: 搜索关键词（商品名称/品牌/分类/显示名称/第三方产品编码，可选）
        """
        logger.info(f"[product_list] 查询商品列表: page={page}, page_size={page_size}, keyword={keyword}")
        db = SessionLocal()
        try:
            query = db.query(Product).filter(Product.is_published == True)

            if keyword:
                from sqlalchemy import or_
                query = query.filter(
                    or_(
                        Product.name.contains(keyword),
                        Product.brand.contains(keyword),
                        Product.category_name.contains(keyword),
                        Product.display_name.contains(keyword),
                        Product.third_party_code.contains(keyword),
                    )
                )

            total = query.count()
            products = query.order_by(Product.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

            logger.info(f"[product_list] 查询完成: total={total}, 返回{len(products)}条")
            return {
                "success": True,
                "data": {
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                    "products": [
                        {
                            "id": p.id,
                            "name": p.name,
                            "brand": p.brand,
                            "third_party_code": p.third_party_code,
                            "face_value": float(p.face_value),
                            "charge_type": p.charge_type,
                            "category_name": p.category_name,
                            "display_name": p.display_name,
                            "selling_price": float(p.selling_price),
                            "is_published": p.is_published,
                        }
                        for p in products
                    ]
                }
            }
        finally:
            db.close()

    @mcp.tool()
    def product_get(product_id: int) -> dict:
        """查询商品详情

        Args:
            product_id: 商品ID
        """
        logger.info(f"[product_get] 查询商品详情: product_id={product_id}")
        db = SessionLocal()
        try:
            product = db.query(Product).filter(Product.id == product_id, Product.is_published == True).first()
            if not product:
                logger.warning(f"[product_get] 商品不存在或未上架: product_id={product_id}")
                return {"success": False, "error": "商品不存在"}

            return {
                "success": True,
                "data": {
                    "id": product.id,
                    "name": product.name,
                    "brand": product.brand,
                    "third_party_code": product.third_party_code,
                    "face_value": float(product.face_value),
                    "charge_type": product.charge_type,
                    "category_name": product.category_name,
                    "display_name": product.display_name,
                    "selling_price": float(product.selling_price),
                    "is_published": product.is_published,
                }
            }
        finally:
            db.close()

    @mcp.tool()
    async def order_get(order_id: str) -> dict:
        """查询订单

        Args:
            order_id: 订单ID

        功能:
            - 验证订单存在
            - 微信待支付(pay_channel=wechat, pay_status=pending)：查询微信支付状态，支付成功后自动触发充值
            - 支付宝待支付(pay_channel=alipay, pay_status=pending)：查询支付宝支付状态，支付成功后自动触发充值
            - 已支付充值中(pay_status=paid, order_status=processing)：查询第三方充值状态
            - 其他状态：直接返回
        """
        logger.info(f"[order_get] 查询订单: order_id={order_id}")
        db = SessionLocal()
        try:
            order = db.query(Order).filter(Order.order_id == order_id).with_for_update().first()
            if not order:
                logger.warning(f"[order_get] 订单不存在: order_id={order_id}")
                return {"success": False, "error": "订单不存在"}

            # 待支付：按支付渠道查询支付状态
            if order.pay_status == "pending" and order.pay_channel:
                if order.pay_channel == "wechat":
                    logger.info(f"[order_get] 微信订单待支付，查询微信支付状态: order_id={order_id}")
                    try:
                        wechat_client = get_wechat_client()
                        result = await wechat_client.query_order(out_trade_no=order_id)
                        if result.get("error"):
                            logger.warning(f"[order_get] 微信支付查询失败: order_id={order_id}, result={result}")
                        else:
                            trade_state = result.get("trade_state", "")
                            order.wechat_info = json.dumps(result, ensure_ascii=False)

                            if trade_state == "SUCCESS":
                                if result.get("transaction_id"):
                                    order.wechat_transaction_id = result["transaction_id"]
                                db.refresh(order)
                                if order.pay_status != "pending":
                                    logger.info(f"[order_get] 订单状态已变更，跳过充值: order_id={order_id}, pay_status={order.pay_status}")
                                else:
                                    amount_data = result.get("amount", {})
                                    total_paid = amount_data.get("total", 0)
                                    expected_fen = int(float(order.total_amount) * 100)
                                    if total_paid != expected_fen:
                                        logger.error(f"[order_get] 微信支付金额不匹配: order_id={order_id}, expected={expected_fen}, actual={total_paid}")
                                    else:
                                        logger.info(f"[order_get] 微信支付成功，触发充值: order_id={order_id}")
                                        order.pay_status = "paid"
                                        order.order_status = "processing"
                                        if result.get("transaction_id"):
                                            order.wechat_transaction_id = result["transaction_id"]
                                        db.commit()
                                        db.refresh(order)

                                        product = db.query(Product).filter(Product.id == order.product_id).first()
                                        if product:
                                            await _trigger_charge(db, order, product)
                                            db.refresh(order)

                            elif trade_state in ("CLOSED", "REVOKED", "PAYERROR"):
                                logger.info(f"[order_get] 微信订单已关闭/撤销/支付失败: order_id={order_id}, trade_state={trade_state}")
                                order.pay_status = "closed"
                                order.order_status = "fail"
                                db.commit()
                                db.refresh(order)

                    except Exception as e:
                        logger.warning(f"[order_get] 微信支付查询异常: order_id={order_id}, error={str(e)}")
                        try:
                            db.commit()
                        except Exception:
                            pass

                else:
                    logger.info(f"[order_get] 支付宝订单待支付，查询支付宝状态: order_id={order_id}")
                    try:
                        result = await call_alipay_tool("query-alipay-payment", {"outTradeNo": order_id})
                        alipay_info = _extract_alipay_info(result)
                        if alipay_info.get("trade_no"):
                            order.alipay_trade_no = alipay_info["trade_no"]
                        order.alipay_info = json.dumps(result, ensure_ascii=False)
                        raw_text = result.get("raw_text", "")
                        if "TRADE_SUCCESS" in raw_text or "支付成功" in raw_text:
                            db.refresh(order)
                            if order.pay_status != "pending":
                                logger.info(f"[order_get] 订单状态已变更，跳过充值: order_id={order_id}, pay_status={order.pay_status}")
                            else:
                                logger.info(f"[order_get] 支付宝支付成功，触发充值: order_id={order_id}")
                                order.pay_status = "paid"
                                order.order_status = "processing"
                                db.commit()
                                db.refresh(order)

                                product = db.query(Product).filter(Product.id == order.product_id).first()
                                if product:
                                    await _trigger_charge(db, order, product)
                                    db.refresh(order)
                    except Exception as e:
                        logger.warning(f"[order_get] 支付宝支付查询失败: order_id={order_id}, error={str(e)}")
                        try:
                            db.commit()
                        except Exception:
                            pass

                return {
                    "success": True,
                    "data": {
                        "order_id": order.order_id,
                        "product_id": order.product_id,
                        "quantity": order.quantity,
                        "total_amount": float(order.total_amount) if order.total_amount else None,
                        "account_no": order.account_no,
                        "pay_status": order.pay_status,
                        "pay_channel": order.pay_channel,
                        "order_status": order.order_status,
                        "wechat_transaction_id": order.wechat_transaction_id,
                        "alipay_trade_no": order.alipay_trade_no,
                        "card_info": order.card_info,
                        "ret_code": order.ret_code,
                        "ret_msg": order.ret_msg,
                    }
                }

            # 已支付充值中：查询第三方充值状态
            if order.pay_status == "paid" and order.order_status == "processing":
                logger.info(f"[order_get] 订单充值中，查询第三方状态: order_id={order_id}")
                try:
                    result = await call_query_api(
                        euser_id=settings.fixed_euser_id,
                        euser_order_no=order_id,
                        timestamp=int(time.time() * 1000),
                    )
                    logger.info(f"[order_get] 第三方查询接口返回: order_id={order_id}, result={result}")
                    if "orderStatus" in result:
                        order.order_status = result["orderStatus"]
                    if "cardInfo" in result:
                        order.card_info = result["cardInfo"]
                    if "retCode" in result:
                        order.ret_code = result["retCode"]
                    if "retMsg" in result:
                        order.ret_msg = result["retMsg"]
                    db.commit()
                    db.refresh(order)
                except Exception as e:
                    logger.warning(f"[order_get] 第三方查询接口调用失败: order_id={order_id}, error={str(e)}")

            return {
                "success": True,
                "data": {
                    "order_id": order.order_id,
                    "product_id": order.product_id,
                    "quantity": order.quantity,
                    "total_amount": float(order.total_amount) if order.total_amount else None,
                    "account_no": order.account_no,
                    "pay_status": order.pay_status,
                    "order_status": order.order_status,
                    "alipay_trade_no": order.alipay_trade_no,
                    "card_info": order.card_info,
                    "ret_code": order.ret_code,
                    "ret_msg": order.ret_msg,
                }
            }
        finally:
            db.close()

    @mcp.tool()
    async def order_create(items: list, account_no: str) -> dict:
        """创建订单（同时返回微信和支付宝支付链接，用户访问时确定支付方式）

        Args:
            items: 商品列表，每项包含 product_id（商品ID）和 quantity（购买数量），如 [{"product_id": 1, "quantity": 2}]
            account_no: 充值账号（手机号）
        """
        logger.info(f"[order_create] 创建订单: items={items}, account_no={account_no}")
        db = SessionLocal()
        try:
            created_orders = []
            payment_links = []

            for item in items:
                product_id = item.get("product_id")
                quantity = item.get("quantity")

                product = db.query(Product).filter(Product.id == product_id).first()
                if not product:
                    logger.warning(f"[order_create] 商品不存在: product_id={product_id}")
                    return {"success": False, "error": f"商品不存在: {product_id}"}
                if not product.is_published:
                    logger.warning(f"[order_create] 商品未上架: product_id={product_id}")
                    return {"success": False, "error": f"商品未上架: {product_id}"}

                existing = db.query(Order).filter(
                    Order.account_no == account_no,
                    Order.product_id == product_id,
                    Order.quantity == quantity,
                    Order.pay_status == "pending",
                ).first()
                if existing:
                    if existing.created_at and existing.created_at < datetime.utcnow() - timedelta(minutes=10):
                        logger.info(f"[order_create] pending订单已超时，删除旧订单: order_id={existing.order_id}, created_at={existing.created_at}")
                        db.delete(existing)
                        db.flush()
                    else:
                        logger.info(f"[order_create] 该账号已有同商品pending订单: order_id={existing.order_id}, product_id={product_id}, account_no={account_no}")
                        created_orders.append({
                            "order_id": existing.order_id,
                            "product_id": existing.product_id,
                            "quantity": existing.quantity,
                            "total_amount": float(existing.total_amount) if existing.total_amount else None,
                            "pay_status": existing.pay_status,
                            "pay_channel": existing.pay_channel,
                            "order_status": existing.order_status,
                        })
                        payment_links.append({
                            "order_id": existing.order_id,
                            "wxpay_url": f"{settings.base_url}/orders/wxpay/{existing.order_id}",
                            "alipay_url": f"{settings.base_url}/orders/pay/{existing.order_id}",
                        })
                        continue

                timestamp = str(int(time.time() * 1000))[-13:]
                unique_part = uuid.uuid4().hex[:19]
                order_id = timestamp + unique_part
                ts = int(time.time() * 1000)

                total_amount = product.selling_price * quantity

                order = Order(
                    order_id=order_id,
                    euser_id=settings.fixed_euser_id,
                    product_id=product_id,
                    third_party_code=product.third_party_code,
                    quantity=quantity,
                    total_amount=total_amount,
                    pay_status="pending",
                    account_no=account_no,
                    request_timestamp=ts,
                    order_status="pending",
                )
                db.add(order)
                logger.info(f"[order_create] 订单已创建: order_id={order_id}, product_id={product_id}, quantity={quantity}, total_amount={float(total_amount)}")
                created_orders.append({
                    "order_id": order_id,
                    "product_id": product_id,
                    "quantity": quantity,
                    "total_amount": float(total_amount),
                    "pay_status": "pending",
                    "pay_channel": None,
                    "order_status": "pending",
                })
                payment_links.append({
                    "order_id": order_id,
                    "wxpay_url": f"{settings.base_url}/orders/wxpay/{order_id}",
                    "alipay_url": f"{settings.base_url}/orders/pay/{order_id}",
                })

            db.commit()

            logger.info(f"[order_create] 订单创建完成: total_count={len(created_orders)}")

            return {
                "success": True,
                "data": {
                    "orders": created_orders,
                    "total_count": len(created_orders),
                    "payment_links": payment_links,
                }
            }
        finally:
            db.close()


# ==================== 内部工具（完整CRUD）====================

def register_internal_tools(mcp: FastMCP):
    """注册内部 MCP Tools（包含商品管理等写入操作，商品查询不受上架限制）"""

    @mcp.tool()
    def product_list(
        page: int = 1,
        page_size: int = 10,
        keyword: str = None,
        is_published: bool = None,
    ) -> dict:
        """查询商品列表（内部，可查看所有商品）

        Args:
            page: 页码（默认1）
            page_size: 每页数量（默认10）
            keyword: 搜索关键词（商品名称/品牌/分类/显示名称/第三方产品编码，可选）
            is_published: 上架状态筛选（可选）
        """
        logger.info(f"[product_list/internal] 查询商品列表: page={page}, page_size={page_size}, keyword={keyword}, is_published={is_published}")
        db = SessionLocal()
        try:
            query = db.query(Product)

            if keyword:
                from sqlalchemy import or_
                query = query.filter(
                    or_(
                        Product.name.contains(keyword),
                        Product.brand.contains(keyword),
                        Product.category_name.contains(keyword),
                        Product.display_name.contains(keyword),
                        Product.third_party_code.contains(keyword),
                    )
                )

            if is_published is not None:
                query = query.filter(Product.is_published == is_published)

            total = query.count()
            products = query.order_by(Product.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

            logger.info(f"[product_list/internal] 查询完成: total={total}, 返回{len(products)}条")
            return {
                "success": True,
                "data": {
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                    "products": [
                        {
                            "id": p.id,
                            "name": p.name,
                            "brand": p.brand,
                            "third_party_code": p.third_party_code,
                            "face_value": float(p.face_value),
                            "charge_type": p.charge_type,
                            "category_name": p.category_name,
                            "display_name": p.display_name,
                            "selling_price": float(p.selling_price),
                            "is_published": p.is_published,
                        }
                        for p in products
                    ]
                }
            }
        finally:
            db.close()

    @mcp.tool()
    def product_get(product_id: int) -> dict:
        """查询商品详情（内部，可查看未上架商品）

        Args:
            product_id: 商品ID
        """
        logger.info(f"[product_get/internal] 查询商品详情: product_id={product_id}")
        db = SessionLocal()
        try:
            product = db.query(Product).filter(Product.id == product_id).first()
            if not product:
                logger.warning(f"[product_get/internal] 商品不存在: product_id={product_id}")
                return {"success": False, "error": "商品不存在"}

            return {
                "success": True,
                "data": {
                    "id": product.id,
                    "name": product.name,
                    "brand": product.brand,
                    "third_party_code": product.third_party_code,
                    "face_value": float(product.face_value),
                    "charge_type": product.charge_type,
                    "category_name": product.category_name,
                    "display_name": product.display_name,
                    "selling_price": float(product.selling_price),
                    "is_published": product.is_published,
                }
            }
        finally:
            db.close()

    @mcp.tool()
    def product_add(name: str, third_party_code: str, selling_price: float, face_value: float = 0, charge_type: int = 1, brand: str = None, category_name: str = None, display_name: str = None) -> dict:
        """新增商品

        Args:
            name: 商品名称
            third_party_code: 第三方产品编码
            selling_price: 售价
            face_value: 面值（默认0）
            charge_type: 充值类型：1直充 2卡密（默认1）
            brand: 品牌（可选）
            category_name: 分类名称（可选）
            display_name: 显示名称（可选）
        """
        logger.info(f"[product_add] 新增商品: name={name}, third_party_code={third_party_code}, face_value={face_value}, selling_price={selling_price}")
        db = SessionLocal()
        try:
            if db.query(Product).filter(Product.third_party_code == third_party_code).first():
                logger.warning(f"[product_add] 第三方产品编码已存在: {third_party_code}")
                return {"success": False, "error": "第三方产品编码已存在"}

            product = Product(
                name=name,
                brand=brand,
                third_party_code=third_party_code,
                face_value=face_value,
                charge_type=charge_type,
                category_name=category_name,
                display_name=display_name,
                selling_price=selling_price,
            )
            db.add(product)
            db.commit()
            db.refresh(product)

            logger.info(f"[product_add] 商品创建成功: id={product.id}, name={product.name}")
            return {
                "success": True,
                "data": {
                    "id": product.id,
                    "name": product.name,
                    "brand": product.brand,
                    "third_party_code": product.third_party_code,
                    "face_value": float(product.face_value),
                    "charge_type": product.charge_type,
                    "category_name": product.category_name,
                    "display_name": product.display_name,
                    "selling_price": float(product.selling_price),
                    "is_published": product.is_published,
                }
            }
        finally:
            db.close()

    @mcp.tool()
    def product_publish(product_id: int) -> dict:
        """上架/下架商品

        Args:
            product_id: 商品ID
        """
        logger.info(f"[product_publish] 切换商品上下架状态: product_id={product_id}")
        db = SessionLocal()
        try:
            product = db.query(Product).filter(Product.id == product_id).first()
            if not product:
                logger.warning(f"[product_publish] 商品不存在: product_id={product_id}")
                return {"success": False, "error": "商品不存在"}

            product.is_published = not product.is_published
            db.commit()

            logger.info(f"[product_publish] 商品状态更新: product_id={product.id}, is_published={product.is_published}")
            return {
                "success": True,
                "data": {
                    "id": product.id,
                    "is_published": product.is_published,
                }
            }
        finally:
            db.close()

    @mcp.tool()
    def product_delete(product_id: int) -> dict:
        """删除商品

        Args:
            product_id: 商品ID
        """
        logger.info(f"[product_delete] 删除商品: product_id={product_id}")
        db = SessionLocal()
        try:
            product = db.query(Product).filter(Product.id == product_id).first()
            if not product:
                logger.warning(f"[product_delete] 商品不存在: product_id={product_id}")
                return {"success": False, "error": "商品不存在"}

            db.delete(product)
            db.commit()

            logger.info(f"[product_delete] 商品删除成功: product_id={product_id}")
            return {"success": True, "message": "商品删除成功"}
        finally:
            db.close()
