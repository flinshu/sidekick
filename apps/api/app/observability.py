"""Langfuse 接入：追踪 Agent run + 工具调用 + JIT 指令 + token usage + tenant。

设计：
- 一次 chat 请求 → 一个 Langfuse trace
- trace 名为 "chat:<conversation_id>"，metadata 含 tenant_id、model
- 每个工具调用 → 一个 child span
- 最终 LLM 完成 → end trace 并附 usage / cost 估算
- 没配 LANGFUSE_SECRET_KEY 时整套观测变成 noop（开发体验友好）
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from .config import get_settings

logger = logging.getLogger(__name__)


_client = None
_disabled = False


def _get_client():
    global _client, _disabled
    if _disabled:
        return None
    if _client is not None:
        return _client
    settings = get_settings()
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        logger.info("Langfuse 未配置 keys，追踪 disabled")
        _disabled = True
        return None
    try:
        from langfuse import Langfuse  # type: ignore[import-not-found]

        _client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        logger.info("Langfuse client connected to %s", settings.langfuse_host)
    except Exception as e:  # noqa: BLE001
        logger.warning("Langfuse 初始化失败：%s ; 追踪 disabled", e)
        _disabled = True
        _client = None
    return _client


def trace_turn(
    *,
    conversation_id: str,
    tenant_id: str,
    user_message: str,
    trace_data: dict[str, Any],
) -> None:
    """把一次 run_turn 的完整 trace 上报。

    trace_data 应包含 sidekick_agent.TurnTrace 序列化字段。
    """
    client = _get_client()
    if client is None:
        return
    try:
        # langfuse v2 API
        trace = client.trace(
            name=f"chat:{conversation_id[:8]}",
            user_id=tenant_id,
            metadata={
                "tenant_id": tenant_id,
                "conversation_id": conversation_id,
                "successful_model": trace_data.get("successful_model"),
                "iterations": trace_data.get("iterations"),
                "completed": trace_data.get("completed"),
                "hit_max_iterations": trace_data.get("hit_max_iterations"),
                "fallback_count": len(trace_data.get("fallback_events") or []),
                "validation_retries": trace_data.get("validation_retries"),
            },
            input={"user_message": user_message},
            output={"final_content": trace_data.get("final_content")},
        )
        # 给整体加 usage / cost
        usage = trace_data.get("usage") or {}
        if usage:
            trace.update(
                usage={
                    "input": usage.get("prompt_tokens", 0),
                    "output": usage.get("completion_tokens", 0),
                    "total": usage.get("total_tokens", 0),
                }
            )
        # 每次工具调用 → child span
        for tc in trace_data.get("tool_calls") or []:
            trace.span(
                name=f"tool:{tc.get('name')}",
                metadata={
                    "ok": tc.get("ok"),
                    "requires_confirmation": tc.get("requires_confirmation"),
                    "error": tc.get("error"),
                },
                input={"arguments": tc.get("arguments")},
            )
        # JIT 指令片段
        for idx, jit in enumerate(trace_data.get("jit_instructions_seen") or []):
            trace.span(name=f"jit:{idx}", input={"instruction_preview": jit[:200]})
        client.flush()
    except Exception as e:  # noqa: BLE001
        logger.warning("Langfuse trace 上报失败：%s", e)
