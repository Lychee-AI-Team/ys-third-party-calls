import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from app.config import settings
from app.routers import hello, product, order


class PathNormalizeMiddleware(BaseHTTPMiddleware):
    """路径规范化中间件，处理双斜杠问题"""
    async def dispatch(self, request: Request, call_next):
        # 规范化路径：移除双斜杠
        if request.url.path.startswith("//"):
            request.scope["path"] = request.url.path[1:]
            request.scope["raw_path"] = request.scope["raw_path"][1:]
        return await call_next(request)


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
    root_path=settings.root_path,
)

# 添加路径规范化中间件
app.add_middleware(PathNormalizeMiddleware)

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