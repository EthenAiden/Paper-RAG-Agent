"""MySQL 数据库连接与 ORM 模型（按设计文档规范）"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Text, BigInteger, Integer, SmallInteger, DateTime, func
from app.core.config import get_settings

settings = get_settings()

# 连接池配置
engine = create_async_engine(
    settings.mysql_url,
    echo=settings.app_debug,
    pool_size=10,           # 连接池大小
    max_overflow=20,        # 最大溢出连接数
    pool_timeout=30,        # 获取连接超时时间
    pool_recycle=1800,      # 连接回收时间（秒）
    pool_pre_ping=True,     # 连接前检查可用性
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Document(Base):
    """文档信息表：存储上传文档的元数据"""
    __tablename__ = "document"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(50), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    minio_bucket: Mapped[str] = mapped_column(String(100), nullable=False)
    minio_object_path: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    # status: 0-解析中, 1-已完成, 2-解析失败
    error_msg: Mapped[str | None] = mapped_column(String(500), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class DocumentChunk(Base):
    """文档分块表：存储文档拆分后的文本块元数据"""
    __tablename__ = "document_chunk"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    doc_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())


class Conversation(Base):
    """会话表：存储问答会话元数据"""
    __tablename__ = "conversation"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ConversationMessage(Base):
    """会话消息表：存储会话中的问答消息"""
    __tablename__ = "conversation_message"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conv_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user / assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    references: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON 格式存储引用信息
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())


class UserFeedback(Base):
    """用户反馈表：存储用户对回答的反馈"""
    __tablename__ = "user_feedback"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 1-好评, 0-差评
    comment: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
