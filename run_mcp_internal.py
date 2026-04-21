#!/usr/bin/env python3
"""MCP Server 启动脚本 — 内部实例（完整CRUD）

端口 8001，注册全部工具（含商品管理、订单创建），仅供内部使用。
"""
import uvicorn
from app.config import settings
from app.mcp.server import get_internal_mcp_app

if __name__ == "__main__":
    app = get_internal_mcp_app()
    uvicorn.run(app, host=settings.mcp_host, port=settings.mcp_internal_port)
