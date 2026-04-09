FROM python:3.13-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 复制代码
COPY app/ ./app/
COPY sql/ ./sql/

# 暴露端口
EXPOSE 1000

# 启动命令
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "1000"]