"""
数据库配置和连接
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

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


async def run_migrations(conn):
    """运行数据库迁移 - 添加缺失的列"""
    # 检查并添加 task_config.locked_count 列
    try:
        result = conn.execute(text("PRAGMA table_info(task_config)"))
        columns = [row[1] for row in result.fetchall()]
        
        if 'locked_count' not in columns:
            conn.execute(text("ALTER TABLE task_config ADD COLUMN locked_count INTEGER DEFAULT 0"))
            print("✓ 已添加 task_config.locked_count 列")
    except Exception as e:
        # 表可能不存在，create_all 会创建
        pass


async def init_db():
    """初始化数据库，创建所有表"""
    async with engine.begin() as conn:
        # 先创建所有表
        await conn.run_sync(Base.metadata.create_all)
        # 运行迁移（添加新列）
        await conn.run_sync(run_migrations)


async def get_db() -> AsyncSession:
    """获取数据库session"""
    async with async_session() as session:
        yield session

