"""HIL（Human-in-the-Loop）状态机。

设计：
- M1 的 update_*/save_*/create_* 工具是"两阶段"的——第 1 次 call 返回 preview + token，
  第 2 次带 confirmed_token 真正执行
- M1 在 Agentic Loop 内部完成（Agent "自己确认自己"，是 bug）
- M2 把第 1 阶段的返回**钉到数据库 + 中断 Agent loop**，等用户在 UI 上点确认/取消，
  路由再恢复 Agent，把 ConfirmDecision 作为 user message 注入消息流，让 Agent 继续
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import AgentCheckpoint


async def save_checkpoint(
    session: AsyncSession,
    *,
    conversation_id: str,
    tenant_id: str,
    confirmation_token: str,
    tool_name: str,
    tool_args: dict[str, Any],
    preview: dict | None,
) -> AgentCheckpoint:
    cp = AgentCheckpoint(
        conversation_id=conversation_id,
        tenant_id=tenant_id,
        confirmation_token=confirmation_token,
        tool_name=tool_name,
        tool_args=tool_args,
        preview=preview,
    )
    session.add(cp)
    await session.flush()
    return cp


async def get_checkpoint(
    session: AsyncSession, *, confirmation_token: str, tenant_id: str
) -> AgentCheckpoint | None:
    stmt = select(AgentCheckpoint).where(
        AgentCheckpoint.confirmation_token == confirmation_token,
        AgentCheckpoint.tenant_id == tenant_id,
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def get_confirmed_tokens(
    session: AsyncSession, *, conversation_id: str, tenant_id: str
) -> set[str]:
    """返回这个会话里所有 decision='confirm' 的 confirmation_token 集合。"""
    stmt = select(AgentCheckpoint.confirmation_token).where(
        AgentCheckpoint.conversation_id == conversation_id,
        AgentCheckpoint.tenant_id == tenant_id,
        AgentCheckpoint.decision == "confirm",
    )
    res = await session.execute(stmt)
    return {row for row in res.scalars().all()}


async def get_pending_checkpoints(
    session: AsyncSession, *, conversation_id: str, tenant_id: str
) -> list[AgentCheckpoint]:
    """该会话里尚未决定的（decision 为 NULL）checkpoint，按创建时间升序。"""
    stmt = (
        select(AgentCheckpoint)
        .where(
            AgentCheckpoint.conversation_id == conversation_id,
            AgentCheckpoint.tenant_id == tenant_id,
            AgentCheckpoint.decision.is_(None),
        )
        .order_by(AgentCheckpoint.created_at.asc())
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def record_decision(
    session: AsyncSession, *, checkpoint: AgentCheckpoint, decision: str
) -> None:
    checkpoint.decision = decision
    checkpoint.decided_at = datetime.utcnow()
