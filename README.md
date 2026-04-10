# ys-third-party-calls

第三方充值服务接口，支持商品管理、订单创建与查询，对接第三方充值平台。

## 功能特性

- 商品管理：商品的增删改查、上下架
- 订单管理：创建订单、查询订单、删除订单
- 第三方接口对接：充值接口、订单查询接口
- 签名验证：MD5签名机制
- MCP Server：支持 AI 客户端（小龙虾等）通过 MCP 协议调用服务

## 技术栈

- Python 3.13
- FastAPI 0.110.0
- SQLAlchemy 2.0.38
- MySQL (PyMySQL)
- Docker

## 目录结构

```
ys-third-party-calls/
├── app/
│   ├── config.py          # 配置管理
│   ├── database.py        # 数据库连接
│   ├── main.py            # 应用入口
│   ├── models/            # 数据模型
│   │   ├── product.py     # 商品模型
│   │   └── order.py       # 订单模型
│   ├── schemas/           # Pydantic模型
│   │   ├── product.py     # 商品Schema
│   │   └── order.py       # 订单Schema
│   ├── routers/           # 路由模块
│   │   ├── hello.py       # 健康检查
│   │   ├── product.py     # 商品路由
│   │   └── order.py       # 订单路由
│   ├── mcp/               # MCP Server 模块
│   │   ├── __init__.py    # 模块初始化
│   │   ├── server.py      # FastMCP Server 定义
│   │   └── tools.py       # MCP Tools 定义
│   └── utils/             # 工具模块
│       ├── security.py    # 密码加密
│       ├── sign.py        # 签名生成
│       └── third_party.py # 第三方API调用
├── sql/
│   ├── init.sql           # 初始化脚本
│   ├── products.sql       # 商品表
│   └── orders.sql         # 订单表
├── run_mcp.py             # MCP Server 启动脚本
├── Dockerfile             # Web 服务 Dockerfile
├── Dockerfile.mcp         # MCP 服务 Dockerfile
├── docker-compose.yml     # Web 服务 Docker Compose
├── docker-compose.mcp.yml # MCP 服务 Docker Compose
├── requirements.txt
└── .env                   # 环境配置（不提交到Git）
```

## 本地开发

### 1. 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows
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
ROOT_PATH=                          # 反向代理路径前缀，本地开发留空

# 固定客户编码
FIXED_EUSER_ID=1642

# 第三方API配置
APIKEY=your_apikey_here
CALLBACK_URL=http://your-domain/callback

# MySQL数据库配置
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=ys-third-party-calls
```

### 3. 初始化数据库

```bash
mysql -u root -p < sql/init.sql
```

### 4. 启动服务

#### Web API 服务（端口 1000）

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 1000
```

访问 API 文档：http://localhost:1000/docs

#### MCP Server（端口 8000）

```bash
python run_mcp.py
```

MCP 端点：http://localhost:8000/mcp

两个服务可同时运行，端口互不冲突。

## Docker 部署

### 方式一：本地构建并导出

```bash
# 构建镜像
docker-compose build

# 导出镜像
docker save ys-third-party-calls-app:latest -o ys-third-party-calls-app.tar

# 上传到服务器
scp ys-third-party-calls-app.tar user@server:/path/to/deploy/

# 服务器加载镜像
docker load -i ys-third-party-calls-app.tar

# 启动容器
docker run -d --name ys-third-party-calls -p 1000:1000 --env-file .env ys-third-party-calls-app:latest
```

### 方式二：服务器直接构建

```bash
# 上传代码到服务器
scp -r app sql requirements.txt Dockerfile docker-compose.yml .env user@server:/path/to/deploy/

# 服务器上构建并启动
docker-compose up -d
```

### 常用命令

```bash
docker-compose up -d        # 后台启动
docker-compose logs -f      # 查看日志
docker-compose down         # 停止并移除容器
docker-compose restart      # 重启服务
```


测试环境 `.env` 配置：
```env
ROOT_PATH=/ys-third-party-calls
```

## API 接口

### 商品管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /products/addProduct | 新增商品 |
| GET | /products/listProduct | 商品列表 |
| GET | /products/getProduct/{id} | 商品详情 |
| PUT | /products/updateProduct/{id} | 修改商品 |
| PUT | /products/publishProduct/{id} | 上架/下架 |
| DELETE | /products/deleteProduct/{id} | 删除商品 |

### 订单管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /orders/addOrder | 创建订单 |
| GET | /orders/getOrder | 查询订单 |
| DELETE | /orders/deleteOrder | 删除订单 |

### 健康检查

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /health | 健康检查 |

## 签名规则

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

## 注意事项

1. `.env` 文件包含敏感信息，不要提交到 Git
2. 生产环境建议关闭 `DEBUG=true`
3. 第三方API需要配置IP白名单
4. 只能删除 `order_status=fail` 的订单

---

## MCP Server

基于 FastMCP 框架实现的 MCP Server，支持 AI 客户端通过 MCP 协议调用服务。

### 技术栈

- **FastMCP** - 简化 MCP Server 开发的 Python 框架
- **Streamable HTTP** - MCP 新一代传输协议，支持 HTTP 远程调用

### MCP Tools 列表

| Tool | 参数 | 说明 |
|------|------|------|
| `product_add` | name, third_party_code, description? | 新增商品 |
| `product_list` | page?, page_size?, keyword?, is_published? | 商品列表 |
| `product_get` | product_id | 商品详情 |
| `product_publish` | product_id | 上架/下架 |
| `product_delete` | product_id | 删除商品 |
| `order_create` | product_id, quantity, account_no | 创建订单（调用第三方充值） |
| `order_get` | order_id | 查询订单（自动调用第三方更新状态） |
| `order_delete` | order_id | 删除订单（仅限失败订单） |

### Docker 部署 MCP

```bash
# 构建 MCP 镜像
docker-compose -f docker-compose.mcp.yml build

# 启动 MCP 服务
docker-compose -f docker-compose.mcp.yml up -d

# 查看日志
docker-compose -f docker-compose.mcp.yml logs -f
```

### 小龙虾接入配置

1. 打开小龙虾客户端设置
2. 进入 **MCP Servers** 配置
3. 添加新的 MCP Server：
   - **名称**: `ys-third-party-calls`
   - **类型**: `HTTP` 或 `Streamable HTTP`
   - **地址**: `http://localhost:8000/mcp`（本地）或 `http://服务器IP:8000/mcp`（远程）
4. 保存并启用

在小龙虾对话中可测试：
- "帮我查看商品列表"
- "创建一个订单，商品ID是2，数量1，充值账号13800138000"

### 客户端连接示例

#### Python MCP 客户端

```python
import asyncio
import httpx
import json

async def call_mcp_tool(tool_name: str, arguments: dict):
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json, text/event-stream'
    }

    async with httpx.AsyncClient(timeout=30) as client:
        # 初始化
        resp = await client.post('http://localhost:8000/mcp', json={
            'jsonrpc': '2.0', 'method': 'initialize',
            'params': {'protocolVersion': '2024-11-05', 'capabilities': {},
                       'clientInfo': {'name': 'test', 'version': '1.0'}},
            'id': 1
        }, headers=headers)

        session_id = resp.headers.get('mcp-session-id')
        if session_id:
            headers['mcp-session-id'] = session_id

        # 调用 Tool
        resp = await client.post('http://localhost:8000/mcp', json={
            'jsonrpc': '2.0', 'method': 'tools/call',
            'params': {'name': tool_name, 'arguments': arguments},
            'id': 2
        }, headers=headers)

        for line in resp.text.split('\n'):
            if line.startswith('data:'):
                return json.loads(line[5:].strip())

# 使用示例
asyncio.run(call_mcp_tool('product_list', {'page': 1, 'page_size': 10}))
```