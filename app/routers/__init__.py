from app.routers.hello import router as hello_router
from app.routers.product import router as product_router
from app.routers.order import router as order_router

__all__ = ["hello_router", "product_router", "order_router"]