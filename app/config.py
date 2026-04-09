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

    # 固定客户编码（用于订单管理）
    fixed_euser_id: str = "1001"

    # 第三方API配置
    apikey: str = "apikey"
    callback_url: str = "http://127.0.0.1/callback"

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