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