# ys-third-party-calls

第三方充值服务，对接 007ka 平台进行商品充值，集成微信支付和支付宝支付完成支付流程。双服务架构：Web API + MCP Server（双实例），共享代码但独立运行。

## 功能特性

- 商品管理：商品的增删改查、上下架
- 订单管理：创建订单、查询订单
- 双渠道支付：微信 Native 支付 + 支付宝网页支付，创建订单时同时返回两种支付链接，用户访问时确定支付方式
- 第三方接口对接：007ka 充值接口、订单查询接口
- 签名验证：MD5 签名机制
- MCP Server：双实例架构（对外只读 + 内部全量），支持 AI 客户端通过 MCP 协议调用服务

## 技术栈

- Python 3.13
- FastAPI + Uvicorn
- SQLAlchemy + PyMySQL
- FastMCP（Streamable HTTP 传输协议）
- httpx（异步 HTTP 客户端）
- cryptography（RSA 签名 + AES-256-GCM 解密）
- MySQL
- Docker

## 目录结构

```
ys-third-party-calls/
├── app/
│   ├── config.py              # 配置管理（pydantic-settings）
│   ├── database.py            # 数据库连接
│   ├── main.py                # Web API 入口
│   ├── models/                # SQLAlchemy 数据模型
│   │   ├── product.py         # 商品模型
│   │   └── order.py           # 订单模型
│   ├── schemas/               # Pydantic 请求/响应模型
│   │   ├── product.py
│   │   └── order.py
│   ├── routers/               # FastAPI 路由
│   │   ├── hello.py           # 健康检查
│   │   ├── product.py         # 商品路由
│   │   └── order.py           # 订单路由（含支付回调、二维码页面）
│   ├── mcp/                   # MCP Server 模块
│   │   ├── server.py          # FastMCP 双实例定义
│   │   ├── tools.py           # MCP Tools 定义（public + internal）
│   │   ├── alipay_client.py   # 支付宝 MCP SSE 客户端
│   │   └── wechat/            # 微信支付模块
│   │       ├── __init__.py
│   │       └── client.py      # 微信支付 v3 API 客户端
│   └── utils/                 # 工具模块
│       ├── sign.py            # MD5 签名/验签
│       └── third_party.py     # 007ka 第三方 API 调用
├── sql/
│   ├── init.sql               # 数据库初始化入口
│   ├── products.sql           # 商品表
│   └── orders.sql             # 订单表
├── run_mcp.py                 # 对外 MCP Server 启动（端口 8000）
├── run_mcp_internal.py        # 内部 MCP Server 启动（端口 8001）
├── Dockerfile                 # Web 服务 Dockerfile
├── Dockerfile.mcp             # MCP 服务 Dockerfile
├── docker-compose.yml         # Web 服务编排
├── docker-compose.mcp.yml     # MCP 服务编排
├── requirements.txt
└── .env                       # 环境配置（不提交到 Git）
```

## 业务流程

### 订单生命周期

```
创建订单(pay_status=pending, pay_channel=NULL)
  → 同时返回 wxpay_url 和 alipay_url
  → 用户访问支付链接时锁定 pay_channel（微信或支付宝）
  → 用户完成支付
  → 支付回调/主动查询确认支付成功(pay_status=paid)
  → 触发 007ka 第三方充值(order_status=processing)
  → 第三方回调确认(order_status=success/fail)
```

### 状态字段

| 字段 | 值 | 说明 |
|------|-----|------|
| `pay_status` | `pending` | 待支付 |
| | `paid` | 已支付 |
| | `closed` | 已关闭（微信订单关闭/撤销/支付失败） |
| `pay_channel` | `NULL` | 未确定（创建时） |
| | `wechat` | 微信支付 |
| | `alipay` | 支付宝 |
| `order_status` | `pending` | 待处理 |
| | `processing` | 充值中 |
| | `success` | 充值成功 |
| | `fail` | 充值失败 |

### 并发安全

- 支付链接端点（`/pay/{id}`、`/wxpay/{id}`）使用 `with_for_update()` 行级锁防竞态
- pay_channel 锁定后不可切换；支付 API 失败时回滚 pay_channel 为 NULL 避免死锁
- 支付回调使用行级锁 + 二次状态检查防止重复充值
- 创建订单时防重复：同账号+商品+数量的 pending 订单 10 分钟内复用

## 本地开发

### 1. 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
```

### 2. 配置环境变量

创建 `.env` 文件：

```env
# 应用配置
APP_NAME=ys-third-party-calls
APP_VERSION=1.0.0
DEBUG=true

# 服务配置
HOST=0.0.0.0
PORT=1000
MCP_HOST=0.0.0.0
MCP_PORT=8000
MCP_INTERNAL_PORT=8001
ROOT_PATH=                          # 反向代理路径前缀，本地开发留空
BASE_URL=http://localhost:1000      # 服务基础URL（用于生成支付链接）

# 固定客户编码
FIXED_EUSER_ID=1001

# 第三方API配置
APIKEY=your_apikey_here
CALLBACK_URL=http://your-domain/callback

# 支付宝 MCP 服务配置
DASHSCOPE_API_KEY=your_dashscope_key
ALIPAY_MCP_SSE_URL=https://dashscope.aliyuncs.com/api/v1/mcps/alipay/sse
ALIPAY_NOTIFY_URL=https://your-domain/orders/callback/alipay
ALIPAY_RETURN_URL=https://your-domain/orders/pay/success

# 微信支付配置
WECHAT_APPID=wx...
WECHAT_MCHID=1234567890
WECHAT_PRIVATE_KEY=wechatpay_private_key.pem   # 商户私钥文件路径（相对于项目根目录）
WECHAT_SERIAL_NO=...
WECHAT_API_V3_KEY=...
WECHAT_NOTIFY_URL=https://your-domain/orders/callback/wechat

# MySQL数据库配置
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=ys_third_party
```

### 3. 初始化数据库

```bash
mysql -u root -p ys_third_party < sql/init.sql
```

### 4. 启动服务

#### Web API（端口 1000）

```bash
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 1000
```

API 文档：http://localhost:1000/docs

#### 对外 MCP Server（端口 8000，只读 + 创建订单）

```bash
python3 run_mcp.py
```

#### 内部 MCP Server（端口 8001，全量工具）

```bash
python3 run_mcp_internal.py
```

三个服务可同时运行，端口互不冲突。

## Docker 部署

### Web API 服务

```bash
docker-compose up -d        # 后台启动
docker-compose logs -f      # 查看日志
docker-compose down         # 停止
docker-compose restart      # 重启
```

### MCP 服务

```bash
docker-compose -f docker-compose.mcp.yml up -d
docker-compose -f docker-compose.mcp.yml logs -f
```

### 导出镜像部署

```bash
docker-compose build
docker save ys-third-party-calls-app:latest -o app.tar
scp app.tar user@server:/path/to/deploy/
# 服务器上
docker load -i app.tar
docker run -d --name ys-app -p 1000:1000 --env-file .env ys-third-party-calls-app:latest
```

测试环境 `.env` 配置：
```env
ROOT_PATH=/ys-third-party-calls
BASE_URL=https://lychee.thinkarts.cn/ys-third-party-calls
```

## API 接口

### 商品管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /products/addProduct | 新增商品 |
| GET | /products/listProduct | 商品列表（分页、搜索、状态筛选） |
| GET | /products/getProduct/{id} | 商品详情 |
| PUT | /products/updateProduct/{id} | 修改商品 |
| PUT | /products/publishProduct/{id} | 上架/下架 |
| DELETE | /products/deleteProduct/{id} | 删除商品 |

### 订单管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /orders/addOrder | 创建订单（返回双渠道支付链接） |
| GET | /orders/getOrder?order_id=xxx | 查询订单（自动同步支付/充值状态） |

### 支付相关

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /orders/pay/{order_id} | 支付宝支付（锁定渠道后重定向） |
| GET | /orders/wxpay/{order_id} | 微信支付二维码页面（锁定渠道后展示） |
| POST | /orders/callback/alipay | 支付宝支付回调 |
| POST | /orders/callback/wechat | 微信支付回调 |
| POST | /orders/callback | 第三方充值回调 |

### 健康检查

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /health | 健康检查 |

## MCP Server

基于 FastMCP 框架，双实例架构实现权限隔离。

### 实例说明

| 实例 | 端口 | 用途 | 可用工具 |
|------|------|------|----------|
| **public**（对外） | 8000 | 对外暴露，安全 | product_list, product_get, order_get, order_create |
| **internal**（内部） | 8001 | 仅内部使用 | 全部工具（含 product_add, product_publish, product_delete） |

### MCP Tools 列表

#### 对外工具（public + internal 均可调用）

| Tool | 参数 | 说明 |
|------|------|------|
| `product_list` | page?, page_size?, keyword?, is_published? | 查询商品列表 |
| `product_get` | product_id | 查询商品详情 |
| `order_get` | order_id | 查询订单（自动同步支付/充值状态） |
| `order_create` | items, account_no | 创建订单（返回双渠道支付链接） |

#### 内部工具（仅 internal 实例）

| Tool | 参数 | 说明 |
|------|------|------|
| `product_add` | name, third_party_code, cost_price, selling_price, description? | 新增商品 |
| `product_publish` | product_id | 上架/下架切换 |
| `product_delete` | product_id | 删除商品 |

### 客户端接入

#### 对外接入（public）

- **地址**: `http://localhost:8000/mcp`
- **类型**: Streamable HTTP
- 适用于 AI 客户端对外服务场景，只能查询和创建订单

#### 内部接入（internal）

- **地址**: `http://localhost:8001/mcp`
- **类型**: Streamable HTTP
- 适用于内部管理场景，可操作商品和订单

#### Python 客户端示例

```python
import asyncio
import httpx
import json

async def call_mcp_tool(base_url: str, tool_name: str, arguments: dict):
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json, text/event-stream'
    }

    async with httpx.AsyncClient(timeout=30) as client:
        # 初始化
        resp = await client.post(f'{base_url}/mcp', json={
            'jsonrpc': '2.0', 'method': 'initialize',
            'params': {'protocolVersion': '2024-11-05', 'capabilities': {},
                       'clientInfo': {'name': 'test', 'version': '1.0'}},
            'id': 1
        }, headers=headers)

        session_id = resp.headers.get('mcp-session-id')
        if session_id:
            headers['mcp-session-id'] = session_id

        # 调用 Tool
        resp = await client.post(f'{base_url}/mcp', json={
            'jsonrpc': '2.0', 'method': 'tools/call',
            'params': {'name': tool_name, 'arguments': arguments},
            'id': 2
        }, headers=headers)

        for line in resp.text.split('\n'):
            if line.startswith('data:'):
                return json.loads(line[5:].strip())

# 使用示例
asyncio.run(call_mcp_tool('http://localhost:8000', 'product_list', {'page': 1, 'page_size': 10}))
```

## 签名规则

第三方 API 签名机制：

1. 参数名按字母顺序排序
2. 拼接参数值
3. 结尾加 apikey
4. MD5 加密后小写

示例：
```
参数: {"euserOrderNo": "123", "timestamp": "1695775129000"}
拼接: 1231695775129000 + apikey
签名: md5("1231695775129000apikey")
```

验证使用 `hmac.compare_digest` 防时序攻击。

## 注意事项

1. `.env` 文件包含敏感信息，不要提交到 Git
2. 生产环境建议关闭 `DEBUG=true`
3. 第三方 API 需要配置 IP 白名单
4. 微信支付商户私钥文件（`.pem`）需放置在项目根目录
5. 支付宝 MCP 通过 SSE 连接 DashScope，每次调用创建新客户端连接
6. 对外 MCP（8000）仅暴露查询和创建订单工具，商品管理操作请使用内部 MCP（8001）
