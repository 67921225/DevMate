from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from .config import DATABASE_URL

class Base(DeclarativeBase):
    pass

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # SQLite 专属，其他数据库（MySQL/PostgreSQL）去掉这行
    echo = True # 可选，设置为 True 会在控制台打印所有执行的 SQL 语句，方便调试
    )  

SessionLocal = sessionmaker(
    autocommit=False,   # 关闭自动提交，推荐手动 commit
    autoflush=False,    # 关闭自动刷新，推荐手动 flush
    bind=engine
    )

