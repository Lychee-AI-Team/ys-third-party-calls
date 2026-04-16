"""MCP Tools 定义（装饰器风格）"""
import json
import logging
import time
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from fastmcp import FastMCP
from app.database import SessionLocal
from app.models.product import Product
from app.models.order import Order
from app.utils.third_party import call_charge_api, call_query_api
from app.mcp.alipay_client import call_alipay_tool
from app.config import settings
import time
import uuid

logger = logging.getLogger(__name__)


def register_tools(mcp: FastMCP):
    """注册所有 MCP Tools"""

    # ==================== 商品管理 ====================

    @mcp.tool()
    def product_add(name: str, third_party_code: str, cost_price: float, selling_price: float, description: str = None) -> dict:
        """新增商品

        Args:
            name: 商品名称
            third_party_code: 第三方产品编码
            cost_price: 成本价
            selling_price: 售价
            description: 商品描述（可选）
        """
        logger.info(f"[product_add] 新增商品: name={name}, third_party_code={third_party_code}, cost_price={cost_price}, selling_price={selling_price}")
        db = SessionLocal()
        try:
            # 检查编码是否已存在
            if db.query(Product).filter(Product.third_party_code == third_party_code).first():
                logger.warning(f"[product_add] 第三方产品编码已存在: {third_party_code}")
                return {"success": False, "error": "第三方产品编码已存在"}

            product = Product(
                name=name,
                third_party_code=third_party_code,
                description=description,
                cost_price=cost_price,
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
                    "third_party_code": product.third_party_code,
                    "cost_price": float(product.cost_price),
                    "selling_price": float(product.selling_price),
                    "is_published": product.is_published,
                }
            }
        finally:
            db.close()

    @mcp.tool()
    def product_list(
        page: int = 1,
        page_size: int = 10,
        keyword: str = None,
        is_published: bool = None
    ) -> dict:
        """查询商品列表

        Args:
            page: 页码（默认1）
            page_size: 每页数量（默认10）
            keyword: 搜索关键词（可选）
            is_published: 上架状态筛选（可选）
        """
        logger.info(f"[product_list] 查询商品列表: page={page}, page_size={page_size}, keyword={keyword}, is_published={is_published}")
        db = SessionLocal()
        try:
            query = db.query(Product)

            if keyword:
                from sqlalchemy import or_
                query = query.filter(
                    or_(
                        Product.name.contains(keyword),
                        Product.third_party_code.contains(keyword),
                    )
                )

            if is_published is not None:
                query = query.filter(Product.is_published == is_published)

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
                            "third_party_code": p.third_party_code,
                            "cost_price": float(p.cost_price),
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
            product = db.query(Product).filter(Product.id == product_id).first()
            if not product:
                logger.warning(f"[product_get] 商品不存在: product_id={product_id}")
                return {"success": False, "error": "商品不存在"}

            return {
                "success": True,
                "data": {
                    "id": product.id,
                    "name": product.name,
                    "third_party_code": product.third_party_code,
                    "description": product.description,
                    "cost_price": float(product.cost_price),
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

    # ==================== 订单管理 ====================

    def _extract_alipay_info(alipay_result: dict) -> dict:
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

        # 2. 从文本中提取（raw_text 或其他文本字段）
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
                    # 英文/JSON 格式: trade_no=xxx, trade_no:xxx, "trade_no":"xxx"
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

        # retCode=2 时查询确认
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

    @mcp.tool()
    async def order_create(items: list, account_no: str) -> dict:
        """创建订单（先发起支付宝支付，支付成功后自动充值）

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

                # 验证商品
                product = db.query(Product).filter(Product.id == product_id).first()
                if not product:
                    logger.warning(f"[order_create] 商品不存在: product_id={product_id}")
                    return {"success": False, "error": f"商品不存在: {product_id}"}
                if not product.is_published:
                    logger.warning(f"[order_create] 商品未上架: product_id={product_id}")
                    return {"success": False, "error": f"商品未上架: {product_id}"}

                # 防重复：同一账号+商品+数量已有pending订单则返回已有订单
                existing = db.query(Order).filter(
                    Order.account_no == account_no,
                    Order.product_id == product_id,
                    Order.quantity == quantity,
                    Order.pay_status == "pending",
                ).first()
                if existing:
                    # 检查pending订单是否超过30分钟（支付链接有效期），超时则删除允许重新创建
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
                            "order_status": existing.order_status,
                        })
                        payment_links.append({"order_id": existing.order_id, "pay_url": f"{settings.base_url}/orders/pay/{existing.order_id}"})
                        continue

                # 生成订单ID和时间戳
                timestamp = str(int(time.time() * 1000))[-13:]
                unique_part = uuid.uuid4().hex[:19]
                order_id = timestamp + unique_part
                ts = int(time.time() * 1000)

                # 计算订单总金额
                total_amount = product.selling_price * quantity

                # 保存订单（仅创建，不调用第三方充值）
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
                    "order_status": "pending",
                })

                # 调用支付宝MCP创建支付
                try:
                    alipay_args = {
                        "outTradeNo": order_id,
                        "totalAmount": float(total_amount),
                        "orderTitle": product.name,
                    }
                    alipay_result = await call_alipay_tool("create-web-page-alipay-payment", alipay_args)
                    logger.info(f"[order_create] 支付宝支付创建成功: order_id={order_id}")
                    # 提取支付宝交易号等信息
                    alipay_info = _extract_alipay_info(alipay_result)
                    if alipay_info.get("trade_no"):
                        order.alipay_trade_no = alipay_info["trade_no"]
                    order.alipay_info = json.dumps(alipay_result, ensure_ascii=False)
                    payment_links.append({
                        "order_id": order_id,
                        "pay_url": f"{settings.base_url}/orders/pay/{order_id}",
                    })
                except Exception as e:
                    logger.error(f"[order_create] 支付宝支付创建失败: order_id={order_id}, error={str(e)}")
                    # 支付失败，删除刚创建的订单，避免孤儿订单
                    db.delete(order)
                    created_orders.pop()
                    return {"success": False, "error": f"支付宝支付创建失败: {str(e)}"}

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

    @mcp.tool()
    async def order_get(order_id: str) -> dict:
        """查询订单

        Args:
            order_id: 订单ID

        功能:
            - 验证订单存在
            - 待支付(pay_status=pending)：查询支付宝支付状态，支付成功后自动触发充值
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

            # 待支付：查询支付宝支付状态
            if order.pay_status == "pending":
                logger.info(f"[order_get] 订单待支付，查询支付宝状态: order_id={order_id}")
                try:
                    result = await call_alipay_tool("query-alipay-payment", {"outTradeNo": order_id})
                    # 存储支付宝查询结果
                    alipay_info = _extract_alipay_info(result)
                    if alipay_info.get("trade_no"):
                        order.alipay_trade_no = alipay_info["trade_no"]
                    order.alipay_info = json.dumps(result, ensure_ascii=False)
                    raw_text = result.get("raw_text", "")
                    if "TRADE_SUCCESS" in raw_text or "支付成功" in raw_text:
                        # 再次检查状态，防止并发重复充值
                        db.refresh(order)
                        if order.pay_status != "pending":
                            logger.info(f"[order_get] 订单状态已变更，跳过充值: order_id={order_id}, pay_status={order.pay_status}")
                        else:
                            # 支付成功，更新状态并触发充值
                            logger.info(f"[order_get] 支付宝支付成功，触发充值: order_id={order_id}")
                            order.pay_status = "paid"
                            order.order_status = "processing"
                            db.commit()
                            db.refresh(order)

                            # 触发第三方充值
                            product = db.query(Product).filter(Product.id == order.product_id).first()
                            if product:
                                await _trigger_charge(db, order, product)
                                db.refresh(order)
                except Exception as e:
                    logger.warning(f"[order_get] 支付宝支付查询失败: order_id={order_id}, error={str(e)}")
                    # 即使查询失败，也尝试保存已获取的支付宝信息
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
                        "order_status": order.order_status,
                        "alipay_trade_no": order.alipay_trade_no,
                        "card_info": order.card_info,
                        "ret_code": order.ret_code,
                        "ret_msg": order.ret_msg,
                        "refund_amount": float(order.refund_amount) if order.refund_amount else None,
                        "refund_trade_no": order.refund_trade_no,
                        "out_request_no": order.out_request_no,
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
                    "refund_amount": float(order.refund_amount) if order.refund_amount else None,
                    "refund_trade_no": order.refund_trade_no,
                    "out_request_no": order.out_request_no,
                }
            }
        finally:
            db.close()

    # ==================== 支付宝退款 ====================

    @mcp.tool()
    async def pay_refund(order_id: str, refund_amount: str = None) -> dict:
        """退款（调用支付宝MCP服务，仅限已支付成功的订单）

        Args:
            order_id: 订单ID
            refund_amount: 退款金额（不填则全额退款）
        """
        logger.info(f"[pay_refund] 发起退款: order_id={order_id}, refund_amount={refund_amount}")
        db = SessionLocal()
        try:
            # 验证订单存在且已支付
            order = db.query(Order).filter(Order.order_id == order_id).first()
            if not order:
                logger.warning(f"[pay_refund] 订单不存在: order_id={order_id}")
                return {"success": False, "error": "订单不存在"}

            if order.pay_status != "paid":
                logger.warning(f"[pay_refund] 订单未支付，无法退款: order_id={order_id}, pay_status={order.pay_status}")
                return {"success": False, "error": "只能对已支付的订单发起退款"}

            # 未指定退款金额则全额退款
            amount = refund_amount if refund_amount else float(order.total_amount)

            # 构造退款参数（使用支付宝MCP的参数名）
            import uuid as _uuid
            out_req_no = f"RF{order_id}{_uuid.uuid4().hex[:6]}"
            alipay_args = {
                "outTradeNo": order_id,
                "refundAmount": float(amount),
                "outRequestNo": out_req_no,
            }
            # 如果有支付宝交易号，同时传递以精确退款
            if order.alipay_trade_no:
                alipay_args["tradeNo"] = order.alipay_trade_no
            # 调用支付宝 MCP 退款
            try:
                result = await call_alipay_tool("refund-alipay-payment", alipay_args)
            except Exception as e:
                logger.error(f"[pay_refund] 支付宝MCP退款失败: order_id={order_id}, error={str(e)}")
                return {"success": False, "error": f"支付宝退款失败: {str(e)}"}

            # 更新退款信息到订单
            order.pay_status = "refunded"
            order.refund_amount = Decimal(amount)
            order.out_request_no = out_req_no
            order.refund_info = json.dumps(result, ensure_ascii=False)

            # 尝试从退款结果中提取退款交易号
            refund_info_data = _extract_alipay_info(result)
            if refund_info_data.get("trade_no"):
                order.refund_trade_no = refund_info_data["trade_no"]

            db.commit()

            logger.info(f"[pay_refund] 退款成功: order_id={order_id}, refund_amount={amount}, refund_trade_no={order.refund_trade_no}")

            return {
                "success": True,
                "data": {
                    "order_id": order_id,
                    "refund_amount": amount,
                    "pay_status": "refunded",
                    "refund_trade_no": order.refund_trade_no,
                    "out_request_no": out_req_no,
                    "alipay_result": result,
                }
            }
        finally:
            db.close()
