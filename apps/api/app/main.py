"""FastAPI 主入口。

路由：
- GET  /api/health                健康检查
- GET  /api/tenants               列出可用租户（UI 切换器用）
- GET  /api/conversations         列出当前租户的会话
- GET  /api/conversations/{id}    会话详情含消息
- POST /api/chat                  发起对话（SSE 流式）
- POST /api/confirm               HIL 确认/取消写操作
- GET  /api/metrics/cache         语义缓存指标

所有需租户上下文的路由从请求头 X-Shop-Domain 读，未带或未注册返回 400/404。
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from dataclasses import asdict

from . import cache_metrics, conversations, hil, observability
from .agent_bridge import db_messages_to_history, make_runner_for_tenant, sse_format
from .semantic_cache import get_cache
from .api_models import (
    ChatRequest,
    ConfirmRequest,
    ConversationDetail,
    ConversationSummary,
    MessageOut,
    PendingConfirmation,
    SseEvent,
    TenantInfo,
)
from .config import get_settings
from .db import get_session, init_db
from .tenants import (
    TenantContext,
    TenantNotFoundError,
    TenantTokenMissingError,
    list_tenants,
    resolve_tenant,
)

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.sidekick_log_level.upper())

    app = FastAPI(
        title="Sidekick API",
        version="0.2.0",
        description="POC: 单 Agent + JIT + Shopify 工具集",
    )

    # POC 期 CORS 全开；生产环境收紧
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:3001"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def _startup() -> None:
        await init_db()
        logger.info("Sidekick API started, env=%s", settings.sidekick_env)

    return app


app = create_app()


# ============ 依赖注入 ============


async def get_tenant(x_shop_domain: Annotated[str | None, Header()] = None) -> TenantContext:
    if not x_shop_domain:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="缺少 X-Shop-Domain 请求头（指定要操作哪个 Shopify 店铺）",
        )
    try:
        return resolve_tenant(x_shop_domain)
    except TenantNotFoundError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except TenantTokenMissingError as e:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e


# ============ 路由 ============


@app.get("/api/health")
async def health() -> dict:
    return {"ok": True, "version": "0.2.0"}


@app.get("/api/tenants", response_model=list[TenantInfo])
async def get_tenants() -> list[TenantInfo]:
    return [TenantInfo(**t) for t in list_tenants()]


@app.get("/api/conversations", response_model=list[ConversationSummary])
async def list_conversations_route(
    tenant: TenantContext = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
) -> list[ConversationSummary]:
    rows = await conversations.list_conversations(session, tenant.shop_domain)
    return [
        ConversationSummary(
            id=r.id,
            title=r.title,
            updated_at=r.updated_at,
            message_count=len(r.messages) if "messages" in r.__dict__ else 0,
        )
        for r in rows
    ]


@app.get("/api/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation_route(
    conversation_id: str,
    tenant: TenantContext = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
) -> ConversationDetail:
    conv = await conversations.get_conversation(session, conversation_id, tenant.shop_domain)
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="会话不存在")
    msgs = await conversations.get_messages(session, conversation_id, tenant.shop_domain)
    pending = await hil.get_pending_checkpoints(
        session, conversation_id=conversation_id, tenant_id=tenant.shop_domain
    )
    return ConversationDetail(
        id=conv.id,
        title=conv.title,
        messages=[
            MessageOut(
                role=m.role,
                content=m.content,
                tool_calls=m.tool_calls,
                tool_call_id=m.tool_call_id,
                name=m.name,
                created_at=m.created_at,
            )
            for m in msgs
        ],
        pending_confirmations=[
            PendingConfirmation(
                tool_name=cp.tool_name,
                confirmation_token=cp.confirmation_token,
                preview=cp.preview,
            )
            for cp in pending
        ],
    )


@app.post("/api/chat")
async def chat_route(
    req: ChatRequest,
    tenant: TenantContext = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """发起对话。SSE 流式返回 Agent 进度。

    HIL：写工具 Phase 1 返回 preview 时，自动持久化 AgentCheckpoint + 推
    `confirmation_required` 事件（含真实 token）。前端弹卡片→用户点确认→
    POST /api/confirm 把 decision 写入 DB → 用户可发"已确认"消息再走 /api/chat，
    届时 dispatcher 看到该 token 在白名单里，才允许 Phase 2 真正写。
    """

    async def stream() -> AsyncIterator[bytes]:
        # 1. 加载/创建会话
        conv = await conversations.get_or_create(
            session, req.conversation_id, tenant.shop_domain, title_hint=req.message
        )
        history_rows = await conversations.get_messages(session, conv.id, tenant.shop_domain)
        history = db_messages_to_history(history_rows)
        # 持久化用户消息
        await conversations.append_message(
            session,
            conversation_id=conv.id,
            tenant_id=tenant.shop_domain,
            role="user",
            content=req.message,
        )
        await session.commit()

        # 1.5 加载该会话已确认 token 白名单（HIL 防伪）
        confirmed_tokens = await hil.get_confirmed_tokens(
            session, conversation_id=conv.id, tenant_id=tenant.shop_domain
        )

        # 1.6 语义缓存查询：仅对"全新会话第一句话"启用（避免命中后丢失上下文）
        cache = get_cache()
        cache_hit = None
        is_first_message = len(history) == 0
        if is_first_message and not req.model_override:
            try:
                cache_hit = await cache.get(tenant.shop_domain, req.message)
            except Exception as e:  # noqa: BLE001
                logger.warning("缓存查询失败：%s", e)
        if cache_hit:
            yield sse_format(
                SseEvent(event="conversation_id", data={"conversation_id": conv.id})
            )
            yield sse_format(
                SseEvent(event="token", data={"content": cache_hit["response"]})
            )
            yield sse_format(
                SseEvent(
                    event="done",
                    data={
                        "conversation_id": conv.id,
                        "from_cache": True,
                        "model": "cache",
                        "iterations": 0,
                        "latency_s": 0.0,
                        "usage": {},
                        "completed": True,
                    },
                )
            )
            # 仍持久化 assistant 消息
            await conversations.append_message(
                session,
                conversation_id=conv.id,
                tenant_id=tenant.shop_domain,
                role="assistant",
                content=cache_hit["response"],
            )
            await session.commit()
            return

        # 2. 启动 Agent
        runner, shopify = make_runner_for_tenant(tenant)
        try:
            yield sse_format(
                SseEvent(event="conversation_id", data={"conversation_id": conv.id})
            )
            result = await runner.run_turn(
                req.message,
                history=history,
                task_type=req.task_type or tenant.default_task_type,
                model_override=req.model_override,
                confirmed_tokens=confirmed_tokens,
            )

            # 3. HIL：把 Phase 1 的 pending confirmation 持久化 + 推前端
            for pc in result.trace.pending_confirmations:
                await hil.save_checkpoint(
                    session,
                    conversation_id=conv.id,
                    tenant_id=tenant.shop_domain,
                    confirmation_token=pc["confirmation_token"],
                    tool_name=pc["tool_name"],
                    tool_args=pc["tool_args"],
                    preview=pc["preview"],
                )
            await session.commit()

            for tc in result.trace.tool_calls:
                yield sse_format(SseEvent(event="tool_call", data=tc))
            for pc in result.trace.pending_confirmations:
                yield sse_format(
                    SseEvent(
                        event="confirmation_required",
                        data={
                            "tool_name": pc["tool_name"],
                            "confirmation_token": pc["confirmation_token"],
                            "preview": pc["preview"],
                        },
                    )
                )

            # 4. 持久化 assistant + tool 消息回 DB
            for msg in result.messages:
                if msg.role == "system" or msg.role == "user":
                    continue  # system runner 内部，user 已存
                await conversations.append_message(
                    session,
                    conversation_id=conv.id,
                    tenant_id=tenant.shop_domain,
                    role=msg.role,
                    content=msg.content,
                    tool_calls=msg.tool_calls,
                    tool_call_id=msg.tool_call_id,
                    name=msg.name,
                )
            await session.commit()

            # 4.5 写缓存（首句 + 无写操作 + 无 pending 确认 时缓存）
            should_cache = (
                is_first_message
                and not result.trace.pending_confirmations
                and not any(
                    tc.get("name") in {"update_price", "update_inventory", "save_content", "create_promotion", "create_automation"}
                    for tc in result.trace.tool_calls
                )
                and result.trace.final_content
            )
            if should_cache:
                try:
                    await cache.set(
                        tenant.shop_domain,
                        req.message,
                        result.trace.final_content or "",
                        is_dynamic=any(
                            kw in req.message
                            for kw in ("库存", "今天", "实时", "现在", "刚刚")
                        ),
                        metadata={
                            "model": result.trace.successful_model,
                            "iterations": result.trace.iterations,
                        },
                    )
                except Exception as e:  # noqa: BLE001
                    logger.warning("缓存写入失败：%s", e)

            # 4.6 写工具触发缓存失效
            try:
                write_kw_map = {
                    "update_price": ["价格", "price", "售价"],
                    "update_inventory": ["库存", "inventory", "stock"],
                    "save_content": ["描述", "description", "tag", "SEO", "seo"],
                    "create_promotion": ["促销", "折扣", "promotion", "discount"],
                }
                kws_to_invalidate: set[str] = set()
                for tc in result.trace.tool_calls:
                    if tc.get("ok") and not tc.get("requires_confirmation"):
                        for k in write_kw_map.get(tc["name"], []):
                            kws_to_invalidate.add(k)
                if kws_to_invalidate:
                    n = await cache.invalidate_by_keywords(tenant.shop_domain, list(kws_to_invalidate))
                    if n > 0:
                        logger.info("缓存失效 %d 条 by keywords=%s", n, kws_to_invalidate)
            except Exception as e:  # noqa: BLE001
                logger.warning("缓存失效失败：%s", e)

            # 5. 推 final + 完成事件
            yield sse_format(
                SseEvent(event="token", data={"content": result.trace.final_content or ""})
            )
            yield sse_format(
                SseEvent(
                    event="done",
                    data={
                        "conversation_id": conv.id,
                        "model": result.trace.successful_model,
                        "iterations": result.trace.iterations,
                        "latency_s": result.trace.latency_s,
                        "usage": result.trace.usage,
                        "completed": result.trace.completed,
                    },
                )
            )

            # 6. Langfuse 追踪上报（失败不影响响应）
            try:
                observability.trace_turn(
                    conversation_id=conv.id,
                    tenant_id=tenant.shop_domain,
                    user_message=req.message,
                    trace_data=asdict(result.trace),
                )
            except Exception:  # noqa: BLE001
                logger.exception("Langfuse 上报失败（不影响主流程）")
        except Exception as e:  # noqa: BLE001
            logger.exception("chat 失败")
            yield sse_format(SseEvent(event="error", data={"error": str(e)}))
        finally:
            await shopify.aclose()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
            "Connection": "keep-alive",
        },
    )


@app.post("/api/confirm")
async def confirm_route(
    req: ConfirmRequest,
    tenant: TenantContext = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
) -> dict:
    cp = await hil.get_checkpoint(
        session, confirmation_token=req.confirmation_token, tenant_id=tenant.shop_domain
    )
    if cp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="confirmation token 无效或已失效")
    if cp.decision is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"已经决定过：{cp.decision}")
    await hil.record_decision(session, checkpoint=cp, decision=req.decision)
    await session.commit()
    return {
        "ok": True,
        "decision": req.decision,
        "tool_name": cp.tool_name,
        "note": "M2.5 完整 pause/resume 后会触发 Agent 恢复并执行真正的写操作。当前仅记录决定。",
    }


@app.get("/api/metrics/cache")
async def metrics_cache_route() -> dict:
    return (await cache_metrics.get_metrics()).model_dump()


@app.get("/api/jobs/{task_id}")
async def job_status_route(task_id: str, _tenant: TenantContext = Depends(get_tenant)) -> dict:
    """异步任务状态查询（M2.5）。

    Celery worker 跑 `agent.run_turn_async` 等后台任务，此接口给前端轮询。
    没启动 worker 时调用会返回 pending/unknown。
    """
    try:
        from celery.result import AsyncResult  # type: ignore[import-not-found]
        from worker.celery_app import celery_app  # type: ignore[import-not-found]
    except ImportError:
        return {"task_id": task_id, "status": "unknown", "error": "celery worker not installed"}
    try:
        ar: AsyncResult = AsyncResult(task_id, app=celery_app)
        state = ar.state.lower() if ar.state else "pending"
        # Celery state: PENDING / STARTED / SUCCESS / FAILURE / RETRY / REVOKED
        normalized = {
            "pending": "pending",
            "started": "running",
            "success": "succeeded",
            "failure": "failed",
        }.get(state, state)
        result_payload = None
        error_payload = None
        if ar.successful():
            result_payload = ar.result
        elif ar.failed():
            error_payload = str(ar.result)
        return {
            "task_id": task_id,
            "status": normalized,
            "result": result_payload,
            "error": error_payload,
        }
    except Exception as e:  # noqa: BLE001
        return {"task_id": task_id, "status": "unknown", "error": str(e)}
