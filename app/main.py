import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.config import settings
from app.routers import hello, product, order


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    print(f"服务启动中... 端口: {settings.port}")
    yield
    # 关闭时执行
    print("服务关闭中...")


# 创建FastAPI应用
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="第三方调用服务",
    lifespan=lifespan,
)

# 注册路由
app.include_router(hello.router)
app.include_router(product.router)
app.include_router(order.router)


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )