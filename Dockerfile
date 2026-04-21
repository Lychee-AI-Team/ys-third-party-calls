FROM python:3.13-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 复制代码
COPY app/ ./app/
COPY sql/ ./sql/

# 复制微信支付密钥文件
COPY wechatpay_private_key.pem ./wechatpay_private_key.pem
COPY wechatpay_public_key.pem ./wechatpay_public_key.pem

# 暴露端口
EXPOSE 1000

# 启动命令
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "1000"]