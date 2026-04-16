#!/usr/bin/env python3
"""MCP Server 启动脚本（Streamable HTTP）"""
import uvicorn
from app.config import settings
from app.mcp.server import get_mcp_app

if __name__ == "__main__":
    # 获取带中间件的 MCP HTTP 应用
    app = get_mcp_app()
    # 使用 uvicorn 运行
    uvicorn.run(app, host=settings.mcp_host, port=settings.mcp_port)