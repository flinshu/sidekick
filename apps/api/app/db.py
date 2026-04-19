"""SQLAlchemy 异步引擎 + ORM 模型。

设计要点：
- 所有租户范围数据带 `tenant_id`（= shop_domain）
- 简化：M2 用 SQLAlchemy + asyncpg；M3 视情况上 Alembic 迁移
- session 通过 dependency 注入到 FastAPI 路由
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, AsyncIterator

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .config import get_settings


def _to_async_url(url: str) -> str:
    """把 postgresql:// 自动转成 postgresql+asyncpg:// 给 async engine。"""
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    return url


_engine = None
_session_maker: async_sessionmaker[AsyncSession] | None = None


def get_engine():
    global _engine, _session_maker
    if _engine is None:
        url = _to_async_url(get_settings().database_url)
        _engine = create_async_engine(url, echo=False, pool_pre_ping=True)
        _session_maker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_session_maker() -> async_sessionmaker[AsyncSession]:
    if _session_maker is None:
        get_engine()
    assert _session_maker is not None
    return _session_maker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency."""
    async with get_session_maker()() as session:
        yield session


class Base(DeclarativeBase):
    pass


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    title: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.seq",
    )

    __table_args__ = (Index("ix_conv_tenant_updated", "tenant_id", "updated_at"),)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)  # 顺序
    role: Mapped[str] = mapped_column(String(32), nullable=False)  # user/assistant/tool/system
    content: Mapped[str | None] = mapped_column(Text)
    tool_calls: Mapped[Any | None] = mapped_column(JSON)
    tool_call_id: Mapped[str | None] = mapped_column(String(255))
    name: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")

    __table_args__ = (Index("ix_msg_conv_seq", "conversation_id", "seq"),)


class AgentCheckpoint(Base):
    """保存被 HIL 中断时的 Agent 状态，等用户确认后恢复。"""

    __tablename__ = "agent_checkpoints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    confirmation_token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    tool_args: Mapped[Any] = mapped_column(JSON, nullable=False)
    preview: Mapped[Any | None] = mapped_column(JSON)
    decision: Mapped[str | None] = mapped_column(String(16))  # confirm/cancel/None
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)


class CacheEntry(Base):
    """语义缓存条目（M2 占坑，M3 才会真正使用）。"""

    __tablename__ = "cache_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    query_hash: Mapped[str] = mapped_column(String(128), index=True)
    response: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[Any | None] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


async def init_db() -> None:
    """启动时建表（M2 用；M3 切 Alembic）。"""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
