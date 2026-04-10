# ys-third-party-calls

第三方充值服务接口，支持商品管理、订单创建与查询，对接第三方充值平台。

## 功能特性

- 商品管理：商品的增删改查、上下架
- 订单管理：创建订单、查询订单、删除订单
- 第三方接口对接：充值接口、订单查询接口
- 签名验证：MD5签名机制

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
│   └── utils/             # 工具模块
│       ├── security.py    # 密码加密
│       ├── sign.py        # 签名生成
│       └── third_party.py # 第三方API调用
├── sql/
│   ├── init.sql           # 初始化脚本
│   ├── products.sql       # 商品表
│   └── orders.sql         # 订单表
├── Dockerfile
├── docker-compose.yml
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

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 1000
```

访问 API 文档：http://localhost:1000/docs

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