import httpx
from typing import Dict, Any
from app.config import settings
from app.utils.sign import generate_sign


# 第三方API配置
CHARGE_API_URL = "https://api.virtual.007ka.cn/api/apiCharge"
QUERY_API_URL = "https://api.virtual.007ka.cn/api/queryOrder"
APIKEY = settings.apikey
CALLBACK_URL = settings.callback_url


async def call_charge_api(
    account_no: str,
    buy_num: int,
    euser_id: int,
    euser_order_no: str,
    product_code: str,
    timestamp: int,
) -> Dict[str, Any]:
    """
    调用第三方充值接口

    Args:
        account_no: 充值账号（手机号）
        buy_num: 贅买数量
        euser_id: 客户编码（用户ID）
        euser_order_no: 客户订单号（订单ID，32位唯一）
        product_code: 产品编码（商品的第三方产品编码）
        timestamp: 请求时间戳（毫秒）

    Returns:
        接口响应数据
    """
    params = {
        "accountNo": account_no,
        "buyNum": buy_num,
        "euserId": euser_id,
        "euserOrderNo": euser_order_no,
        "productCode": product_code,
        "timestamp": timestamp,
        "callbackUrl": CALLBACK_URL,
    }

    # 生成签名
    sign = generate_sign(params, APIKEY)
    params["sign"] = sign

    async with httpx.AsyncClient() as client:
        response = await client.post(CHARGE_API_URL, json=params)
        return response.json()


async def call_query_api(
    euser_id: int,
    euser_order_no: str,
    timestamp: int,
) -> Dict[str, Any]:
    """
    调用第三方订单查询接口

    Args:
        euser_id: 用户ID
        euser_order_no: 客户订单号
        timestamp: 请求时间戳（毫秒）

    Returns:
        接口响应数据
    """
    params = {
        "euserId": euser_id,
        "euserOrderNo": euser_order_no,
        "timestamp": timestamp,
    }

    # 生成签名
    sign = generate_sign(params, APIKEY)
    params["sign"] = sign

    async with httpx.AsyncClient() as client:
        response = await client.post(QUERY_API_URL, json=params)
        return response.json()