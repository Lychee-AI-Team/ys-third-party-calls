"""支付宝 MCP 客户端 — 通过 FastMCP Client 连接支付宝远程 SSE 服务"""
import json
import logging
from fastmcp import Client
from fastmcp.client import SSETransport
from app.config import settings

logger = logging.getLogger(__name__)


def get_alipay_client() -> Client:
    """创建支付宝 MCP 客户端"""
    headers = {}
    if settings.dashscope_api_key:
        headers["Authorization"] = f"Bearer {settings.dashscope_api_key}"

    transport = SSETransport(
        url=settings.alipay_mcp_sse_url,
        headers=headers if headers else None,
    )
    client = Client(transport)
    return client


async def call_alipay_tool(tool_name: str, arguments: dict) -> dict:
    """调用支付宝 MCP 工具

    Args:
        tool_name: 支付宝工具名称 (create-web-page-alipay-payment, create-mobile-alipay-payment, query-alipay-payment, refund-alipay-payment, query-alipay-refund, create-alipay-payment-agent)
        arguments: 工具参数

    Returns:
        工具返回结果字典
    """
    client = get_alipay_client()
    async with client:
        result = await client.call_tool(tool_name, arguments)
        # 解析返回内容
        for item in result.content:
            if item.type == "text":
                try:
                    return json.loads(item.text)
                except json.JSONDecodeError:
                    return {"raw_text": item.text}
        return {"error": "支付宝服务无返回内容"}
