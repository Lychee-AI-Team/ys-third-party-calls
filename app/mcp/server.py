"""FastMCP Server 定义"""
from fastmcp import FastMCP
from app.config import settings

# 创建 FastMCP 实例
mcp = FastMCP(
    name="ys-third-party-calls",
    version=settings.app_version,
)

# 导入并注册 Tools
from app.mcp.tools import register_tools
register_tools(mcp)


# 获取 HTTP 应用并添加路径规范化中间件
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class PathNormalizeMiddleware(BaseHTTPMiddleware):
    """路径规范化中间件，处理双斜杠问题"""
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        # 规范化路径：移除开头的双斜杠
        if path.startswith("//"):
            request.scope["path"] = path[1:]
            request.scope["raw_path"] = request.scope["raw_path"][1:]
        return await call_next(request)


# 创建带中间件的 HTTP 应用
def get_mcp_app():
    """获取带路径规范化的 MCP HTTP 应用"""
    app = mcp.http_app()
    app.add_middleware(PathNormalizeMiddleware)
    return app