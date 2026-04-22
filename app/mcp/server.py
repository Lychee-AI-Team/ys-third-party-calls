"""FastMCP Server 定义

双实例架构：
- public：对外 MCP，只注册只读工具（查询商品、查询订单）
- internal：内部 MCP，注册全部工具（含商品CRUD、订单创建）
"""
from fastmcp import FastMCP
from app.config import settings

# ==================== 对外 MCP 实例（只读）====================

public_mcp = FastMCP(
    name="ys-third-party-calls-public",
    version=settings.app_version,
)

from app.mcp.tools import register_public_tools
register_public_tools(public_mcp)


# ==================== 内部 MCP 实例（完整CRUD）====================

internal_mcp = FastMCP(
    name="ys-third-party-calls-internal",
    version=settings.app_version,
)

from app.mcp.tools import register_internal_tools
register_public_tools(internal_mcp)
register_internal_tools(internal_mcp)


# ==================== 通用中间件 ====================

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class PathNormalizeMiddleware(BaseHTTPMiddleware):
    """路径规范化中间件，处理双斜杠问题"""
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith("//"):
            request.scope["path"] = path[1:]
            request.scope["raw_path"] = request.scope["raw_path"][1:]
        return await call_next(request)


class IPWhitelistMiddleware(BaseHTTPMiddleware):
    """IP白名单中间件，限制内部MCP访问来源"""
    async def dispatch(self, request: Request, call_next):
        from starlette.responses import JSONResponse

        client_ip = request.client.host if request.client else None
        allowed_ips = [ip.strip() for ip in settings.mcp_internal_allowed_ips.split(",") if ip.strip()]

        if client_ip not in allowed_ips:
            return JSONResponse(status_code=403, content={"detail": "Access denied"})

        return await call_next(request)


def get_public_mcp_app():
    """获取对外 MCP HTTP 应用（只读工具）"""
    app = public_mcp.http_app()
    app.add_middleware(PathNormalizeMiddleware)
    return app


def get_internal_mcp_app():
    """获取内部 MCP HTTP 应用（全部工具，IP白名单保护）"""
    app = internal_mcp.http_app()
    app.add_middleware(IPWhitelistMiddleware)
    app.add_middleware(PathNormalizeMiddleware)
    return app
