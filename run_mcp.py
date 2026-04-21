#!/usr/bin/env python3
"""MCP Server 启动脚本 — 对外实例（只读工具）

端口 8000，仅注册查询类工具，可安全对外暴露。
"""
import uvicorn
from app.config import settings
from app.mcp.server import get_public_mcp_app

if __name__ == "__main__":
    app = get_public_mcp_app()
    uvicorn.run(app, host=settings.mcp_host, port=settings.mcp_port)
