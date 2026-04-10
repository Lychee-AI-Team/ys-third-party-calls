"""MCP Tools 定义（装饰器风格）"""
from fastmcp import FastMCP
from app.database import SessionLocal
from app.models.product import Product
from app.models.order import Order
from app.utils.third_party import call_charge_api
from app.config import settings
import time
import uuid


def register_tools(mcp: FastMCP):
    """注册所有 MCP Tools"""

    # ==================== 商品管理 ====================

    @mcp.tool()
    def product_add(name: str, third_party_code: str, description: str = None) -> dict:
        """新增商品

        Args:
            name: 商品名称
            third_party_code: 第三方产品编码
            description: 商品描述（可选）
        """
        db = SessionLocal()
        try:
            # 检查编码是否已存在
            if db.query(Product).filter(Product.third_party_code == third_party_code).first():
                return {"success": False, "error": "第三方产品编码已存在"}

            product = Product(
                name=name,
                third_party_code=third_party_code,
                description=description,
            )
            db.add(product)
            db.commit()
            db.refresh(product)

            return {
                "success": True,
                "data": {
                    "id": product.id,
                    "name": product.name,
                    "third_party_code": product.third_party_code,
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
        db = SessionLocal()
        try:
            product = db.query(Product).filter(Product.id == product_id).first()
            if not product:
                return {"success": False, "error": "商品不存在"}

            return {
                "success": True,
                "data": {
                    "id": product.id,
                    "name": product.name,
                    "third_party_code": product.third_party_code,
                    "description": product.description,
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
        db = SessionLocal()
        try:
            product = db.query(Product).filter(Product.id == product_id).first()
            if not product:
                return {"success": False, "error": "商品不存在"}

            product.is_published = not product.is_published
            db.commit()

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
        db = SessionLocal()
        try:
            product = db.query(Product).filter(Product.id == product_id).first()
            if not product:
                return {"success": False, "error": "商品不存在"}

            db.delete(product)
            db.commit()

            return {"success": True, "message": "商品删除成功"}
        finally:
            db.close()

    # ==================== 订单管理 ====================

    @mcp.tool()
    async def order_create(product_id: int, quantity: int, account_no: str) -> dict:
        """创建订单（调用第三方充值接口）

        Args:
            product_id: 商品ID
            quantity: 购买数量
            account_no: 充值账号（手机号）
        """
        db = SessionLocal()
        try:
            # 验证商品
            product = db.query(Product).filter(Product.id == product_id).first()
            if not product:
                return {"success": False, "error": "商品不存在"}
            if not product.is_published:
                return {"success": False, "error": "商品未上架"}

            # 生成订单ID和时间戳
            timestamp = str(int(time.time() * 1000))[-13:]
            unique_part = uuid.uuid4().hex[:19]
            order_id = timestamp + unique_part
            ts = int(time.time() * 1000)

            # 调用第三方充值接口
            try:
                result = await call_charge_api(
                    account_no=account_no,
                    buy_num=quantity,
                    euser_id=settings.fixed_euser_id,
                    euser_order_no=order_id,
                    product_code=product.third_party_code,
                    timestamp=ts,
                )
            except Exception as e:
                return {"success": False, "error": f"第三方接口调用失败: {str(e)}"}

            # 解析响应
            ret_code = result.get("retCode")
            ret_msg = result.get("retMsg")

            # 确定订单状态
            if ret_code == 1 or ret_code == "1":
                order_status = "fail"
            elif ret_code == 0 or ret_code == "0":
                order_status = "processing"
            else:
                order_status = "processing"

            # 保存订单
            order = Order(
                order_id=order_id,
                euser_id=settings.fixed_euser_id,
                product_id=product_id,
                third_party_code=product.third_party_code,
                quantity=quantity,
                account_no=account_no,
                request_timestamp=ts,
                platform_order_no=result.get("orderNo"),
                ret_code=ret_code,
                ret_msg=ret_msg,
                order_status=order_status,
            )
            db.add(order)
            db.commit()

            return {
                "success": True,
                "data": {
                    "order_id": order_id,
                    "order_status": order_status,
                    "ret_code": ret_code,
                    "ret_msg": ret_msg,
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
            - 若订单状态为 processing，调用第三方查询接口更新状态
            - 返回最新订单信息
        """
        from app.utils.third_party import call_query_api
        import logging
        logger = logging.getLogger(__name__)

        db = SessionLocal()
        try:
            order = db.query(Order).filter(Order.order_id == order_id).first()
            if not order:
                return {"success": False, "error": "订单不存在"}

            # 若订单状态不是 processing，直接返回现有数据
            if order.order_status != "processing":
                return {
                    "success": True,
                    "data": {
                        "order_id": order.order_id,
                        "product_id": order.product_id,
                        "quantity": order.quantity,
                        "account_no": order.account_no,
                        "order_status": order.order_status,
                        "card_info": order.card_info,
                        "ret_code": order.ret_code,
                        "ret_msg": order.ret_msg,
                    }
                }

            # 订单状态为 processing，调用第三方查询接口更新状态
            timestamp = int(time.time() * 1000)
            try:
                result = await call_query_api(
                    euser_id=settings.fixed_euser_id,
                    euser_order_no=order_id,
                    timestamp=timestamp,
                )
                logger.info(f"第三方查询接口返回: {result}")

                # 更新订单状态
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
                # 查询失败，返回现有数据
                logger.warning(f"第三方查询接口调用失败: {str(e)}")

            return {
                "success": True,
                "data": {
                    "order_id": order.order_id,
                    "product_id": order.product_id,
                    "quantity": order.quantity,
                    "account_no": order.account_no,
                    "order_status": order.order_status,
                    "card_info": order.card_info,
                    "ret_code": order.ret_code,
                    "ret_msg": order.ret_msg,
                }
            }
        finally:
            db.close()

    @mcp.tool()
    def order_delete(order_id: str) -> dict:
        """删除订单（仅限失败订单）

        Args:
            order_id: 订单ID
        """
        db = SessionLocal()
        try:
            order = db.query(Order).filter(Order.order_id == order_id).first()
            if not order:
                return {"success": False, "error": "订单不存在"}

            if order.order_status != "fail":
                return {"success": False, "error": "只能删除失败的订单"}

            db.delete(order)
            db.commit()

            return {"success": True, "message": "订单删除成功"}
        finally:
            db.close()