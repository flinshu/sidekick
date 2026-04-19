"""异步任务定义（M2 占坑骨架）。

设计：
- 长任务（批量内容生成、跨店铺分析）通过 enqueue 派发到这里
- worker 复用 sidekick_agent 的 AgentRunner，所以行为与同步路径完全一致
- 状态查询走 /api/jobs/<task_id> （M2.5 加）
"""
from __future__ import annotations

import asyncio
import logging

from sidekick_agent import AgentRunner

from .celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="agent.run_turn_async", bind=True)
def run_turn_async(self, *, shop_domain: str, message: str, task_type: str | None = None) -> dict:
    """长任务：跑一次 Agent 对话。返回 trace + final_content。

    用于"批量给 N 个商品写文案"等耗时操作。
    商家通过 /api/chat 时，后端可决定走同步（短任务）还是入队（长任务）。
    """
    from app.tenants import resolve_tenant
    from sidekick_tools import ShopifyClient, ShopifyCredentials

    tenant = resolve_tenant(shop_domain)
    creds = ShopifyCredentials(
        shop_domain=tenant.shop_domain,
        admin_token=tenant.admin_token,
        api_version=tenant.api_version,
    )

    async def go() -> dict:
        async with ShopifyClient(credentials=creds) as shopify:
            runner = AgentRunner(shopify_client=shopify)
            result = await runner.run_turn(
                message,
                task_type=task_type or tenant.default_task_type,
            )
            return {
                "completed": result.trace.completed,
                "final_content": result.trace.final_content,
                "iterations": result.trace.iterations,
                "model": result.trace.successful_model,
                "usage": result.trace.usage,
                "tool_calls_count": len(result.trace.tool_calls),
                "latency_s": result.trace.latency_s,
                "error": result.trace.error,
            }

    return asyncio.run(go())


@celery_app.task(name="cache.invalidate_for_tenant")
def invalidate_for_tenant(shop_domain: str, query_keywords: list[str]) -> dict:
    """写操作触发：失效语义相关的缓存条目。M3 实现。"""
    logger.info("Cache invalidation stub for %s, keywords=%s", shop_domain, query_keywords)
    return {"invalidated": 0, "stub": True}
