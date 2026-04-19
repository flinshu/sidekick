"""AgentRunner 单元测试：mock 掉 LiteLLM + Shopify，验证：
- Agentic Loop 在收到 tool_call 后继续循环，拿到 final content 后终止
- Fallback：主模型失败 → 试下一个
- 结构化输出重试：首次 JSON 无效 → 自动重试
- max_iterations 触发强制终止
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock

import httpx
import pytest

from sidekick_agent import AgentRunner, SalesReport
from sidekick_agent.routing import RouteEntry, RouterConfig
from sidekick_tools import ShopifyClient, ShopifyCredentials


def _creds() -> ShopifyCredentials:
    return ShopifyCredentials(
        shop_domain="test-store.myshopify.com",
        admin_token="shpat_test",
        api_version="2025-04",
    )


def _router_cfg(**overrides) -> RouterConfig:
    defaults = dict(
        default_task_type="analysis",
        routes={
            "analysis": RouteEntry("analysis", "openai:primary", ("openai:fallback",)),
            "content_generation": RouteEntry("content_generation", "openai:primary", ()),
        },
        max_tokens=1024,
        temperature=0.0,
        agent_max_iterations=3,
        agent_max_retries_per_call=1,
    )
    defaults.update(overrides)
    return RouterConfig(**defaults)


def _mk_response(content: str | None = None, tool_calls: list[dict] | None = None, usage: dict | None = None) -> dict:
    msg: dict = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return {
        "choices": [{"message": msg}],
        "usage": usage or {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    }


def _tool_call(name: str, args: dict, call_id: str = "c1") -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }


@pytest.fixture
def shopify_mock_client() -> ShopifyClient:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        q = body.get("query", "")
        # 对任何查询都返回可用数据 + throttle
        if "orders" in q:
            return httpx.Response(
                200,
                json={
                    "data": {"orders": {"edges": [{"node": {"totalPrice": "99.00", "createdAt": "2024-03-01"}}]}},
                    "extensions": {"cost": {"throttleStatus": {"currentlyAvailable": 900, "maximumAvailable": 1000, "restoreRate": 50}}},
                },
            )
        return httpx.Response(
            200,
            json={
                "data": {"shop": {"name": "Test"}},
                "extensions": {"cost": {"throttleStatus": {"currentlyAvailable": 900, "maximumAvailable": 1000, "restoreRate": 50}}},
            },
        )

    return ShopifyClient(
        credentials=_creds(),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


# ===== 1. Agentic Loop 正常完成 =====


@pytest.mark.asyncio
async def test_agentic_loop_completes_with_tool_then_final(monkeypatch, shopify_mock_client: ShopifyClient) -> None:
    # 第一次：LLM 返回 tool_call；第二次：LLM 返回 final content
    responses = [
        _mk_response(
            tool_calls=[_tool_call("query_store_data", {"query": "{ orders(first:1) { edges { node { totalPrice } } } }"})]
        ),
        _mk_response(content="上周销售总额 ¥99。"),
    ]
    acompletion_mock = AsyncMock(side_effect=responses)
    monkeypatch.setattr("sidekick_agent.runner.litellm.acompletion", acompletion_mock)

    runner = AgentRunner(config=_router_cfg(), shopify_client=shopify_mock_client)
    result = await runner.run_turn("上周销量", task_type="analysis")

    assert result.trace.completed is True
    assert result.trace.iterations == 2
    assert result.trace.final_content == "上周销售总额 ¥99。"
    assert len(result.trace.tool_calls) == 1
    assert result.trace.tool_calls[0]["name"] == "query_store_data"
    assert result.trace.jit_instructions_seen  # JIT 指令被捕获
    assert "[JIT:analytics_sales]" in result.trace.jit_instructions_seen[0]


# ===== 2. Fallback 触发 =====


@pytest.mark.asyncio
async def test_fallback_triggers_when_primary_fails(monkeypatch, shopify_mock_client: ShopifyClient) -> None:
    # primary 永远报错，fallback 成功返回 final
    call_log = []

    async def fake_acompletion(**kwargs):
        call_log.append(kwargs["model"])
        if "primary" in kwargs["model"]:
            raise RuntimeError("primary down")
        return _mk_response(content="ok via fallback")

    monkeypatch.setattr("sidekick_agent.runner.litellm.acompletion", fake_acompletion)

    runner = AgentRunner(config=_router_cfg(), shopify_client=shopify_mock_client)
    result = await runner.run_turn("hello", task_type="analysis")

    assert result.trace.completed is True
    assert result.trace.successful_model == "openai:fallback"
    assert len(result.trace.fallback_events) == 1
    # call_log 记录 LiteLLM 格式（openai/name）
    assert call_log[0].endswith("primary")
    assert call_log[-1].endswith("fallback")


# ===== 3. max_iterations 强制终止 =====


@pytest.mark.asyncio
async def test_max_iterations_forces_stop(monkeypatch, shopify_mock_client: ShopifyClient) -> None:
    # LLM 每次都返回 tool_call，永不 final
    def always_tool(**_):
        return _mk_response(
            tool_calls=[_tool_call("query_store_data", {"query": "{ shop { name } }"}, call_id="c")]
        )

    monkeypatch.setattr("sidekick_agent.runner.litellm.acompletion", AsyncMock(side_effect=always_tool))

    runner = AgentRunner(config=_router_cfg(agent_max_iterations=3), shopify_client=shopify_mock_client)
    result = await runner.run_turn("hello", task_type="analysis")

    assert result.trace.completed is False
    assert result.trace.hit_max_iterations is True
    assert result.trace.iterations == 3
    assert len(result.trace.tool_calls) == 3


# ===== 4. 结构化输出重试 =====


@pytest.mark.asyncio
async def test_structured_output_retries_on_invalid_json(monkeypatch, shopify_mock_client: ShopifyClient) -> None:
    # 首次返回不合法 JSON；重试时返回合法的 SalesReport JSON
    valid_report = {
        "period": "2024-03-25~2024-03-31",
        "total_orders": 3,
        "total_revenue": "¥300.00",
        "top_products": [],
        "decliners": [],
        "notes": None,
    }
    responses = [
        _mk_response(content="not a valid json"),  # 初次 final
        _mk_response(content=json.dumps(valid_report, ensure_ascii=False)),  # 重试后 final
    ]

    acompletion_mock = AsyncMock(side_effect=responses)
    monkeypatch.setattr("sidekick_agent.runner.litellm.acompletion", acompletion_mock)

    runner = AgentRunner(config=_router_cfg(), shopify_client=shopify_mock_client)
    result = await runner.run_turn(
        "生成销售报告",
        task_type="analysis",
        structured_output=SalesReport,
    )

    assert result.structured_output is not None
    assert isinstance(result.structured_output, SalesReport)
    assert result.structured_output.total_orders == 3
    assert result.trace.validation_retries >= 1


# ===== 5. 未知工具调用的错误处理 =====


@pytest.mark.asyncio
async def test_unknown_tool_returns_error_not_crash(monkeypatch, shopify_mock_client: ShopifyClient) -> None:
    responses = [
        _mk_response(tool_calls=[_tool_call("unknown_tool", {"x": 1})]),
        _mk_response(content="抱歉，无法完成"),
    ]
    monkeypatch.setattr("sidekick_agent.runner.litellm.acompletion", AsyncMock(side_effect=responses))

    runner = AgentRunner(config=_router_cfg(), shopify_client=shopify_mock_client)
    result = await runner.run_turn("hello", task_type="analysis")

    assert result.trace.completed is True
    assert not result.trace.tool_calls[0]["ok"]
