# 充值服务 MCP Skills

MCP 服务端点：`https://lychee.thinkarts.cn/ys-mcp-server_prod/mcp`

## 连接方式

**必须使用 Streamable HTTP Transport**，不支持 SSE Transport。

```python
from fastmcp import Client
from fastmcp.client import StreamableHttpTransport

transport = StreamableHttpTransport(url="https://lychee.thinkarts.cn/ys-mcp-server_prod/mcp")
client = Client(transport)
```

完整连接示例：

```python
import asyncio, json
from fastmcp import Client
from fastmcp.client import StreamableHttpTransport

async def call_tool(tool_name: str, arguments: dict) -> dict:
    transport = StreamableHttpTransport(url="https://lychee.thinkarts.cn/ys-mcp-server_prod/mcp")
    client = Client(transport)
    async with client:
        result = await client.call_tool(tool_name, arguments)
        for item in result.content:
            if item.type == "text":
                try:
                    return json.loads(item.text)
                except json.JSONDecodeError:
                    return {"raw_text": item.text}
        return {"error": "无返回内容"}
```

## 可用工具

### product_list — 查询商品列表

查询已上架商品，支持关键词搜索。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| page | int | 否 | 页码，默认 1 |
| page_size | int | 否 | 每页数量，默认 10 |
| keyword | string | 否 | 搜索关键词，匹配商品名称/品牌/分类/显示名称/第三方产品编码 |

返回示例：

```json
{
  "success": true,
  "data": {
    "total": 50,
    "page": 1,
    "page_size": 10,
    "products": [
      {
        "id": 1,
        "name": "中国移动话费充值50元",
        "brand": "中国移动",
        "third_party_code": "ZG_YD_50",
        "face_value": 50.0,
        "charge_type": 1,
        "category_name": "话费充值",
        "display_name": "移动50元",
        "selling_price": 49.5,
        "is_published": true
      }
    ]
  }
}
```

### product_get — 查询商品详情

根据商品 ID 查询单个已上架商品的详细信息。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| product_id | int | 是 | 商品 ID |

返回示例：

```json
{
  "success": true,
  "data": {
    "id": 1,
    "name": "中国移动话费充值50元",
    "brand": "中国移动",
    "third_party_code": "ZG_YD_50",
    "face_value": 50.0,
    "charge_type": 1,
    "category_name": "话费充值",
    "display_name": "移动50元",
    "selling_price": 49.5,
    "is_published": true
  }
}
```

失败时 `success` 为 `false`，`error` 字段说明原因（如"商品不存在"）。

### order_create — 创建订单

为指定商品创建充值订单，返回微信和支付宝支付链接。同一账号+商品+数量的 pending 订单在 10 分钟内会复用，不会重复创建。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| items | list | 是 | 商品列表，每项包含 `product_id` 和 `quantity` |
| account_no | string | 是 | 充值账号（手机号） |

输入示例：`{"items": [{"product_id": 1, "quantity": 2}], "account_no": "13800138000"}`

返回示例：

```json
{
  "success": true,
  "data": {
    "orders": [
      {
        "order_id": "1748301234567a1b2c3d4e5f6g7h8i9",
        "product_id": 1,
        "quantity": 2,
        "total_amount": 99.0,
        "pay_status": "pending",
        "pay_channel": null,
        "order_status": "pending"
      }
    ],
    "total_count": 1,
    "payment_links": [
      {
        "order_id": "1748301234567a1b2c3d4e5f6g7h8i9",
        "wxpay_url": "https://lychee.thinkarts.cn/ys-third-party-calls/orders/wxpay/1748301234567a1b2c3d4e5f6g7h8i9",
        "alipay_url": "https://lychee.thinkarts.cn/ys-third-party-calls/orders/pay/1748301234567a1b2c3d4e5f6g7h8i9"
      }
    ]
  }
}
```

失败场景：
- 商品不存在：`{"success": false, "error": "商品不存在: {product_id}"}`
- 商品未上架：`{"success": false, "error": "商品未上架: {product_id}"}`

### order_get — 查询订单

查询订单详情。对于 pending 订单会自动查询支付状态（微信/支付宝），支付成功后自动触发第三方充值。对于 processing 订单会自动查询第三方充值状态。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| order_id | string | 是 | 订单 ID（创建订单时返回的 32 位字符串） |

返回示例：

```json
{
  "success": true,
  "data": {
    "order_id": "1748301234567a1b2c3d4e5f6g7h8i9",
    "product_id": 1,
    "quantity": 2,
    "total_amount": 99.0,
    "account_no": "13800138000",
    "pay_status": "paid",
    "order_status": "processing",
    "alipay_trade_no": "2026052700001234567890",
    "card_info": null,
    "ret_code": 0,
    "ret_msg": "充值中"
  }
}
```

## 业务场景编排

### 场景一：商品查询

用户想了解有哪些可充值的商品，或查询某个商品的详细信息。

**步骤：**

1. 调用 `product_list(keyword=用户描述的关键词)` 搜索商品
2. 如果用户需要某个商品的详细信息，用返回的 `product_id` 调用 `product_get(product_id=...)` 获取详情
3. 将商品名称、面值、售价等信息展示给用户

**示例对话：**
- 用户："有哪些移动话费充值？"
- 调用 `product_list(keyword="移动")` → 返回匹配列表

- 用户："商品 1 是什么？"
- 调用 `product_get(product_id=1)` → 返回商品详情

### 场景二：搜索并下单

用户想充值，需要搜索商品、创建订单、获取支付链接。

**步骤：**

1. 调用 `product_list(keyword=用户需求关键词)` 搜索匹配商品
2. 确认用户要购买的商品（从列表中选 `product_id`）和数量
3. 调用 `order_create(items=[{"product_id": ..., "quantity": ...}], account_no=用户的充值手机号)` 创建订单
4. 将返回的 `wxpay_url` 和 `alipay_url` 提供给用户，用户点击链接完成支付

**示例对话：**
- 用户："帮我充50元移动话费，号码13800138000"
- 调用 `product_list(keyword="移动50")` → 找到 `product_id=1`
- 调用 `order_create(items=[{"product_id": 1, "quantity": 1}], account_no="13800138000")` → 返回支付链接
- 回复用户："请点击以下链接支付：微信支付 / 支付宝"

**注意事项：**
- `account_no` 是充值手机号，务必与用户确认
- 订单金额 = 商品售价(selling_price) × 数量(quantity)，不是面值
- 同一账号+商品+数量的 pending 订单 10 分钟内复用，不会重复创建

### 场景三：订单状态追踪

用户已下单，想了解订单当前进度。

**步骤：**

1. 调用 `order_get(order_id=订单号)` 查询订单
2. 根据 `pay_status` 和 `order_status` 向用户解释当前状态
3. 如果订单仍 pending，告知用户支付链接（可从 `wxpay_url` / `alipay_url` 获取）
4. 如果需要持续追踪，建议用户稍后再次查询

**状态说明：**

| pay_status | order_status | 含义 |
|---|---|---|
| pending | pending | 待支付，用户未完成付款 |
| paid | processing | 已支付，第三方充值进行中 |
| paid | success | 充值成功，流程完成 |
| paid | fail | 充值失败，需人工处理 |
| closed | fail | 支付已关闭/撤销/失败 |
| refunded | - | 已退款 |

**注意：** `order_get` 每次调用都会自动检查支付和充值状态，无需额外操作。如果支付刚完成，调用 `order_get` 会自动触发充值。

## 通用注意事项

- 所有工具返回格式统一：`{"success": true/false, "data"/"error": ...}`
- `charge_type` 含义：1 = 直充（直接充到账号），2 = 卡密（返回充值卡号密码）
- `face_value` 是商品面值，`selling_price` 是实际售价，下单金额以售价为准
- `order_id` 是 32 位字符串（13位时间戳 + 19位UUID），非自增整数
- `account_no` 是充值目标账号（通常为手机号），非用户账号
