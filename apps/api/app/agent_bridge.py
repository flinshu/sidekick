"""把 sidekick_agent.AgentRunner 接到 FastAPI 路由的薄适配层。

负责：
- 按 tenant_context 创建针对该租户的 ShopifyClient
- 把 DB messages → ConversationMessage 列表
- 串流式把 trace 事件转 SSE event
- HIL 中断点检测：写工具返回 requires_confirmation 时暂停 + 持久化 checkpoint
"""
from __future__ import annotations

import json
from typing import AsyncIterator

from sidekick_agent import AgentRunner, ConversationMessage
from sidekick_agent.runner import _extra_kwargs_for, _to_litellm_model  # noqa: F401（间接验证）
from sidekick_tools import ShopifyClient, ShopifyCredentials

from .api_models import SseEvent
from .tenants import TenantContext


def make_runner_for_tenant(tenant: TenantContext) -> tuple[AgentRunner, ShopifyClient]:
    creds = ShopifyCredentials(
        shop_domain=tenant.shop_domain,
        admin_token=tenant.admin_token,
        api_version=tenant.api_version,
    )
    shopify = ShopifyClient(credentials=creds)
    runner = AgentRunner(shopify_client=shopify)
    return runner, shopify


def db_messages_to_history(rows) -> list[ConversationMessage]:
    out: list[ConversationMessage] = []
    for r in rows:
        # system 消息由 runner 自己补，DB 不存
        if r.role == "system":
            continue
        out.append(
            ConversationMessage(
                role=r.role,
                content=r.content,
                tool_calls=r.tool_calls,
                tool_call_id=r.tool_call_id,
                name=r.name,
            )
        )
    return out


def sse_format(event: SseEvent) -> bytes:
    """SSE wire format: 'event: <type>\\ndata: <json>\\n\\n'."""
    payload = json.dumps(event.data, ensure_ascii=False, default=str)
    return f"event: {event.event}\ndata: {payload}\n\n".encode("utf-8")
