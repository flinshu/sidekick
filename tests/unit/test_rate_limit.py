"""验证 rate-limit 退避逻辑：低余量时 _maybe_backoff 会触发 sleep。"""
from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from sidekick_tools import query_store_data
from tests.conftest import make_client, ok_graphql_response


@pytest.mark.asyncio
async def test_backoff_triggered_when_throttle_low(monkeypatch) -> None:
    low_throttle = {"currentlyAvailable": 20, "maximumAvailable": 1000, "restoreRate": 50}

    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(200, json=ok_graphql_response({"shop": {"name": "t"}}, throttle=low_throttle))

    client = make_client(httpx.MockTransport(handler))
    # patch asyncio.sleep 捕获调用
    sleep_mock = AsyncMock()
    monkeypatch.setattr("sidekick_tools.shopify_client.asyncio.sleep", sleep_mock)

    try:
        # 第一次调用：还没有 throttle 状态，不触发 backoff
        r1 = await query_store_data("{ shop { name } }", client=client)
        assert r1.ok is True
        assert sleep_mock.call_count == 0

        # 第二次：记录的 throttle 已经很低，应触发 backoff
        r2 = await query_store_data("{ shop { name } }", client=client)
        assert r2.ok is True
        assert sleep_mock.call_count >= 1
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_no_backoff_when_throttle_healthy(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=ok_graphql_response({"shop": {"name": "t"}}))

    client = make_client(httpx.MockTransport(handler))
    sleep_mock = AsyncMock()
    monkeypatch.setattr("sidekick_tools.shopify_client.asyncio.sleep", sleep_mock)

    try:
        for _ in range(3):
            r = await query_store_data("{ shop { name } }", client=client)
            assert r.ok is True
    finally:
        await client.aclose()
    assert sleep_mock.call_count == 0
