from pydantic_settings import BaseSettings
from typing import Optional
from urllib.parse import quote_plus


class Settings(BaseSettings):
    """应用配置类"""

    # 应用配置
    app_name: str = "ys-third-party-calls"
    app_version: str = "1.0.0"
    debug: bool = True

    # 服务配置
    host: str = "0.0.0.0"
    port: int = 1000
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8000
    mcp_internal_port: int = 8001
    mcp_internal_allowed_ips: str = "127.0.0.1,::1"  # 内部MCP白名单IP，逗号分隔
    root_path: str = ""  # 反向代理路径前缀，如 /ys-third-party-calls
    base_url: str = "https://lychee.thinkarts.cn/ys-third-party-calls"  # 服务基础URL（用于生成支付代理链接等）

    # 固定客户编码（用于订单管理）
    fixed_euser_id: str = "1001"

    # 第三方API配置
    apikey: str = "apikey"
    callback_url: str = "http://127.0.0.1/callback"

    # 支付宝 MCP 服务配置
    dashscope_api_key: str = ""  # DashScope API Key
    alipay_mcp_sse_url: str = "https://dashscope.aliyuncs.com/api/v1/mcps/alipay/sse"
    alipay_notify_url: str = ""  # 支付异步通知地址
    alipay_return_url: str = ""  # 支付同步跳转地址

    # 微信支付配置
    wechat_appid: str = ""                            # 应用ID
    wechat_mchid: str = ""                            # 商户号
    wechat_private_key: str = ""                      # 商户私钥文件路径（相对于项目根目录）
    wechat_serial_no: str = ""                        # 商户证书序列号
    wechat_api_v3_key: str = ""                       # API v3 密钥（回调解密用）
    wechat_notify_url: str = ""                       # 支付结果通知地址
    wechat_public_key: str = ""                       # 微信支付公钥文件路径（回调验签用）

    # MySQL数据库配置（预留，暂不实际连接）
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = ""
    mysql_database: str = "ys_third_party"

    @property
    def database_url(self) -> str:
        """获取数据库连接URL"""
        # 对密码进行 URL 编码，处理特殊字符
        encoded_password = quote_plus(self.mysql_password)
        return f"mysql+pymysql://{self.mysql_user}:{encoded_password}@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()