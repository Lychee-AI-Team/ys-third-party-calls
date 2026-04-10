"""FastMCP Server 定义"""
from fastmcp import FastMCP
from app.config import settings

# 创建 FastMCP 实例
mcp = FastMCP(
    name="ys-third-party-calls",
    version=settings.app_version,
)

# 添加路径规范化中间件（处理双斜杠问题）
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class PathNormalizeMiddleware(BaseHTTPMiddleware):
    """路径规范化中间件，处理双斜杠问题"""
    async def dispatch(self, request: Request, call_next):
        # 规范化路径：移除开头的双斜杠
        if request.url.path.startswith("//"):
            request.scope["path"] = request.url.path[1:]
            request.scope["raw_path"] = request.scope["raw_path"][1:]
        return await call_next(request)


# 获取底层 Starlette app 并添加中间件
mcp_app = mcp.http_app()
mcp_app.add_middleware(PathNormalizeMiddleware)

# 导入并注册 Tools
from app.mcp.tools import register_tools
register_tools(mcp)