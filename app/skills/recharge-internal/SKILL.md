# 内部管理 MCP Skills

内部 MCP 服务端点：`https://lychee.thinkarts.cn/ys-mcp-internal_prod/mcp`

> **访问控制**：IP 白名单保护，仅允许内部网络访问。

## 连接方式

**必须使用 Streamable HTTP Transport**，不支持 SSE Transport。

```python
from fastmcp import Client
from fastmcp.client import StreamableHttpTransport

transport = StreamableHttpTransport(url="https://lychee.thinkarts.cn/ys-mcp-internal_prod/mcp")
client = Client(transport)
```

完整连接示例：

```python
import asyncio, json
from fastmcp import Client
from fastmcp.client import StreamableHttpTransport

async def call_tool(tool_name: str, arguments: dict) -> dict:
    transport = StreamableHttpTransport(url="https://lychee.thinkarts.cn/ys-mcp-internal_prod/mcp")
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

### product_list — 查询商品列表（内部）

查询所有商品（含未上架），支持关键词搜索和上架状态筛选。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| page | int | 否 | 页码，默认 1 |
| page_size | int | 否 | 每页数量，默认 10 |
| keyword | string | 否 | 搜索关键词，匹配商品名称/品牌/分类/显示名称/第三方产品编码 |
| is_published | bool | 否 | 上架状态筛选：`true` 仅上架，`false` 仅未上架，不传则查全部 |

与对外版本的区别：不受上架限制，可查看所有商品；新增 `is_published` 筛选参数。

返回示例：

```json
{
  "success": true,
  "data": {
    "total": 130,
    "page": 1,
    "page_size": 10,
    "products": [
      {
        "id": 495,
        "name": "蜜雪冰城代金券7元（直充）-无票-GF",
        "brand": "蜜雪冰城",
        "third_party_code": "101876",
        "face_value": 7.0,
        "charge_type": 1,
        "category_name": "美食饮品-蜜雪冰城-代金券-7元",
        "display_name": "蜜雪冰城代金券7元直充",
        "selling_price": 6.32,
        "is_published": true
      }
    ]
  }
}
```

### product_get — 查询商品详情（内部）

根据商品 ID 查询单个商品详情（含未上架商品）。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| product_id | int | 是 | 商品 ID |

与对外版本的区别：可查看未上架商品。

返回示例：

```json
{
  "success": true,
  "data": {
    "id": 500,
    "name": "瑞幸咖啡代金券15元（直充）",
    "brand": "瑞幸咖啡",
    "third_party_code": "101900",
    "face_value": 15.0,
    "charge_type": 1,
    "category_name": "美食饮品-瑞幸咖啡-代金券-15元",
    "display_name": "瑞幸咖啡15元直充",
    "selling_price": 14.5,
    "is_published": false
  }
}
```

### product_add — 新增商品

新增一个商品，默认未上架状态。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| name | string | 是 | 商品名称 |
| third_party_code | string | 是 | 第三方产品编码（唯一，重复则报错） |
| selling_price | float | 是 | 售价 |
| face_value | float | 否 | 面值，默认 0 |
| charge_type | int | 否 | 充值类型：1 直充 2 卡密，默认 1 |
| brand | string | 否 | 品牌 |
| category_name | string | 否 | 分类名称 |
| display_name | string | 否 | 显示名称 |

返回示例：

```json
{
  "success": true,
  "data": {
    "id": 501,
    "name": "瑞幸咖啡代金券20元（直充）",
    "brand": "瑞幸咖啡",
    "third_party_code": "101901",
    "face_value": 20.0,
    "charge_type": 1,
    "category_name": "美食饮品-瑞幸咖啡-代金券-20元",
    "display_name": "瑞幸咖啡20元直充",
    "selling_price": 19.5,
    "is_published": false
  }
}
```

失败场景：
- 编码重复：`{"success": false, "error": "第三方产品编码已存在"}`

### product_publish — 上架/下架商品

切换商品的上下架状态（上架变下架，下架变上架）。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| product_id | int | 是 | 商品 ID |

返回示例：

```json
{
  "success": true,
  "data": {
    "id": 501,
    "is_published": true
  }
}
```

失败场景：
- 商品不存在：`{"success": false, "error": "商品不存在"}`

### product_delete — 删除商品

删除指定商品（关联的 pending 订单会级联删除）。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| product_id | int | 是 | 商品 ID |

返回示例：

```json
{
  "success": true,
  "message": "商品删除成功"
}
```

失败场景：
- 商品不存在：`{"success": false, "error": "商品不存在"}`

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

### 场景一：商品管理

管理员需要查看、新增、上下架或删除商品。

**查询所有商品（含未上架）：**

1. 调用 `product_list(is_published=None)` 查看全部商品
2. 调用 `product_list(is_published=False)` 仅查看未上架商品
3. 调用 `product_get(product_id=...)` 查看商品详情

**新增商品并上架：**

1. 调用 `product_add(name=商品名称, third_party_code=编码, selling_price=售价, ...)` 创建商品
2. 调用 `product_publish(product_id=新增商品ID)` 上架商品

**示例对话：**
- 管理员："帮我新增一个瑞幸20元代金券，售价19.5，编码101901"
- 调用 `product_add(name="瑞幸咖啡代金券20元（直充）", third_party_code="101901", selling_price=19.5, face_value=20.0, brand="瑞幸咖啡", charge_type=1)` → 创建成功
- 调用 `product_publish(product_id=新商品ID)` → 上架

- 管理员："把商品 501 下架"
- 调用 `product_publish(product_id=501)` → 切换为下架

- 管理员："删除商品 501"
- 调用 `product_delete(product_id=501)` → 删除成功

### 场景二：搜索并下单

用户想充值，需要搜索商品、创建订单、获取支付链接。

**步骤：**

1. 调用 `product_list(keyword=用户需求关键词)` 搜索匹配商品
2. 确认用户要购买的商品（从列表中选 `product_id`）和数量
3. 调用 `order_create(items=[{"product_id": ..., "quantity": ...}], account_no=用户的充值手机号)` 创建订单
4. 将返回的 `wxpay_url` 和 `alipay_url` 提供给用户，用户点击链接完成支付

**示例对话：**
- 管理员："帮我给 13800138000 充值50元移动话费"
- 调用 `product_list(keyword="移动50")` → 找到 `product_id=1`
- 调用 `order_create(items=[{"product_id": 1, "quantity": 1}], account_no="13800138000")` → 返回支付链接
- 回复："请点击以下链接支付：微信支付 / 支付宝"

### 场景三：订单状态追踪

用户已下单，想了解订单当前进度。

**步骤：**

1. 调用 `order_get(order_id=订单号)` 查询订单
2. 根据 `pay_status` 和 `order_status` 向用户解释当前状态
3. 如果订单仍 pending，告知用户支付链接
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
- 新增商品默认未上架（`is_published=false`），需调用 `product_publish` 上架后才能在对外服务中搜索到
- `product_publish` 是切换操作：上架变下架，下架变上架
- `product_delete` 会级联删除关联的 pending 订单，请确认无待处理订单后再删除
