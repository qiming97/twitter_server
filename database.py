"""
数据库配置和连接
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    settings.DATABASE_URL, 
    echo=settings.DEBUG,
    # 连接池优化配置
    pool_size=10,           # 连接池大小
    max_overflow=20,        # 超过 pool_size 后最多可创建的连接数
    pool_timeout=30,        # 等待连接的超时时间(秒)
    pool_recycle=1800,      # 连接回收时间(秒)，防止连接过期
    pool_pre_ping=True,     # 每次使用前检查连接是否有效
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def init_db():
    """初始化数据库，创建所有表"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncSession:
    """获取数据库session"""
    async with async_session() as session:
        yield session

