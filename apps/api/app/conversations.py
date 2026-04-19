"""会话 CRUD：listing、详情、消息追加。

设计要点：
- 所有查询必须按 tenant_id 过滤（强制租户隔离）
- 会话 ID 自动生成，前端可选传入 conversation_id 续接历史
"""
from __future__ import annotations

import secrets
from typing import Iterable

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import Conversation, Message


def _make_id() -> str:
    return secrets.token_urlsafe(12)


async def list_conversations(session: AsyncSession, tenant_id: str, limit: int = 50) -> list[Conversation]:
    stmt = (
        select(Conversation)
        .where(Conversation.tenant_id == tenant_id)
        .order_by(desc(Conversation.updated_at))
        .limit(limit)
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def get_conversation(
    session: AsyncSession, conversation_id: str, tenant_id: str
) -> Conversation | None:
    stmt = (
        select(Conversation)
        .where(Conversation.id == conversation_id, Conversation.tenant_id == tenant_id)
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def get_or_create(
    session: AsyncSession, conversation_id: str | None, tenant_id: str, title_hint: str | None = None
) -> Conversation:
    if conversation_id:
        existing = await get_conversation(session, conversation_id, tenant_id)
        if existing is not None:
            return existing
    new_id = conversation_id or _make_id()
    conv = Conversation(id=new_id, tenant_id=tenant_id, title=(title_hint or "")[:80] or None)
    session.add(conv)
    await session.flush()
    return conv


async def get_messages(session: AsyncSession, conversation_id: str, tenant_id: str) -> list[Message]:
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id, Message.tenant_id == tenant_id)
        .order_by(Message.seq)
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def next_seq(session: AsyncSession, conversation_id: str) -> int:
    stmt = select(func.coalesce(func.max(Message.seq), 0)).where(
        Message.conversation_id == conversation_id
    )
    res = await session.execute(stmt)
    return int(res.scalar() or 0) + 1


async def append_message(
    session: AsyncSession,
    *,
    conversation_id: str,
    tenant_id: str,
    role: str,
    content: str | None = None,
    tool_calls: list[dict] | None = None,
    tool_call_id: str | None = None,
    name: str | None = None,
) -> Message:
    seq = await next_seq(session, conversation_id)
    m = Message(
        conversation_id=conversation_id,
        tenant_id=tenant_id,
        seq=seq,
        role=role,
        content=content,
        tool_calls=tool_calls,
        tool_call_id=tool_call_id,
        name=name,
    )
    session.add(m)
    return m


async def append_many(
    session: AsyncSession,
    *,
    conversation_id: str,
    tenant_id: str,
    messages: Iterable[dict],
) -> None:
    base = await next_seq(session, conversation_id)
    for offset, m in enumerate(messages):
        session.add(
            Message(
                conversation_id=conversation_id,
                tenant_id=tenant_id,
                seq=base + offset,
                role=m["role"],
                content=m.get("content"),
                tool_calls=m.get("tool_calls"),
                tool_call_id=m.get("tool_call_id"),
                name=m.get("name"),
            )
        )
