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
    """IP白名单中间件，限制内部MCP访问来源，支持 CIDR 子网匹配"""
    async def dispatch(self, request: Request, call_next):
        import ipaddress
        from starlette.responses import JSONResponse

        # 优先从代理头获取真实客户端 IP（Docker NAT / 反向代理场景）
        client_ip = (
            request.headers.get("x-forwarded-for", "").split(",")[0].strip()
            or request.headers.get("x-real-ip", "").strip()
            or (request.client.host if request.client else None)
        )
        if not client_ip:
            return JSONResponse(status_code=403, content={"detail": "Access denied"})

        allowed_ips = [ip.strip() for ip in settings.mcp_internal_allowed_ips.split(",") if ip.strip()]

        try:
            client_addr = ipaddress.ip_address(client_ip)
            for rule in allowed_ips:
                if "/" in rule:
                    if client_addr in ipaddress.ip_network(rule, strict=False):
                        return await call_next(request)
                elif client_ip == rule:
                    return await call_next(request)
        except ValueError:
            pass

        return JSONResponse(status_code=403, content={"detail": "Access denied"})


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
