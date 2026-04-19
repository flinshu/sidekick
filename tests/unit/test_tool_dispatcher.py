"""测试 tool_dispatcher 的 JSON 修复 + dispatch 错误路径。"""
from __future__ import annotations

import json

import pytest

from sidekick_agent.tool_dispatcher import (
    ToolDispatchError,
    _try_repair_truncated_json,
    dispatch_tool_call,
    serialize_tool_result,
)
from sidekick_tools import ToolResult


def test_repair_missing_closing_brace() -> None:
    raw = '{"a": 1, "b": {"c": 2}'  # 缺 1 个 }
    out = _try_repair_truncated_json(raw)
    assert out == {"a": 1, "b": {"c": 2}}


def test_repair_missing_array_and_brace() -> None:
    raw = '{"variables": {"ids": ["x", "y"]'  # 缺 ]} → 实际只缺 }，[]已闭合
    out = _try_repair_truncated_json(raw)
    assert out == {"variables": {"ids": ["x", "y"]}}


def test_repair_long_truncation_returns_none() -> None:
    # 缺 6 个 } —— 超过容忍上限
    raw = "{" * 7 + '"x": 1'
    assert _try_repair_truncated_json(raw) is None


def test_repair_balanced_returns_none() -> None:
    # 已经平衡，不需要修复
    raw = '{"a": 1}'
    assert _try_repair_truncated_json(raw) is None


@pytest.mark.asyncio
async def test_dispatch_unknown_tool() -> None:
    result = await dispatch_tool_call("nonexistent", {"x": 1})
    assert result.ok is False
    assert "未知工具" in (result.error or "")


@pytest.mark.asyncio
async def test_dispatch_invalid_json() -> None:
    result = await dispatch_tool_call("query_store_data", "not-json-at-all")
    assert result.ok is False
    assert "JSON" in (result.error or "")


def test_serialize_tool_result_truncates_large_data() -> None:
    big = {"x": "y" * 20000}
    r = ToolResult(ok=True, data=big, jit_instruction="x")
    s = serialize_tool_result(r, max_chars=500)
    assert "truncated" in s


@pytest.mark.asyncio
async def test_dispatch_rejects_unauthorized_confirmed_token() -> None:
    """HIL 防伪：写工具带 confirmed_token 但不在白名单里 → 拒绝。"""
    result = await dispatch_tool_call(
        "update_price",
        {"variant_id": "gid://x", "new_price": "10", "confirmed_token": "FAKE"},
        confirmed_tokens=set(),
    )
    assert result.ok is False
    assert "未授权" in (result.error or "")


@pytest.mark.asyncio
async def test_dispatch_allows_authorized_confirmed_token(monkeypatch) -> None:
    """带的 token 在白名单里 → 走正常流程（这里会因网络失败但说明 dispatcher 没拦截）。"""
    result = await dispatch_tool_call(
        "create_promotion",
        {
            "title": "T",
            "discount_code": "X",
            "percentage_off": 20,
            "confirmed_token": "REAL",
            "confirmation_token": "REAL",
        },
        confirmed_tokens={"REAL"},
    )
    # 不会被 dispatcher 拒；只可能因 Shopify 网络失败而 ok=False
    assert "未授权" not in (result.error or "")


@pytest.mark.asyncio
async def test_dispatch_phase1_no_token_passes_through() -> None:
    """没 confirmed_token 的写工具 Phase 1 不受 HIL 检查影响。"""
    # 不打 Shopify（默认 client 会失败连接），但应该能进入 dispatcher 不被 HIL 拦
    result = await dispatch_tool_call(
        "update_price",
        {"variant_id": "gid://x", "new_price": "10"},
        confirmed_tokens=set(),
    )
    # 只要不被 HIL 拦截即可——可能因网络失败 ok=False，但 error 不应包含"未授权"
    assert "未授权" not in (result.error or "")
