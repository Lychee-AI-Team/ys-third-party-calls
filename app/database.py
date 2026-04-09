from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import settings

# 创建数据库引擎（预留，暂不实际连接）
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    echo=settings.debug,
    pool_recycle=3600,
    connect_args={
        "connect_timeout": 30,
    },
)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建基类
Base = declarative_base()


def get_db():
    """获取数据库会话依赖"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()