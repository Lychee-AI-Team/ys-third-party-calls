#!/usr/bin/env python3
"""MCP Server 启动脚本（Streamable HTTP）"""
from app.mcp.server import mcp

if __name__ == "__main__":
    # Streamable HTTP 模式运行
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)