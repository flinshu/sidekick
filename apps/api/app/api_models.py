"""HTTP / SSE 数据契约。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str
    task_type: str | None = None
    model_override: str | None = None


class ConfirmRequest(BaseModel):
    conversation_id: str
    confirmation_token: str
    decision: Literal["confirm", "cancel"]
    note: str | None = None


class TenantInfo(BaseModel):
    shop_domain: str
    display_name: str
    locale: str


class MessageOut(BaseModel):
    role: str
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    name: str | None = None
    created_at: datetime | None = None


class ConversationSummary(BaseModel):
    id: str
    title: str | None
    updated_at: datetime
    message_count: int


class PendingConfirmation(BaseModel):
    tool_name: str
    confirmation_token: str
    preview: dict[str, Any] | None = None
    note: str | None = None


class ConversationDetail(BaseModel):
    id: str
    title: str | None
    messages: list[MessageOut]
    pending_confirmations: list[PendingConfirmation] = []


# SSE 事件类型（前端用 Vercel AI SDK 风格的 data stream protocol）
class SseEvent(BaseModel):
    event: str  # "token" / "tool_call" / "tool_result" / "confirmation_required" / "done" / "error"
    data: Any = Field(default_factory=dict)


class CacheMetrics(BaseModel):
    total_queries: int
    hits: int
    misses: int
    hit_rate_1h: float
    hit_rate_24h: float
