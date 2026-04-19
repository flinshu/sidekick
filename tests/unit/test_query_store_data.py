from __future__ import annotations

import httpx
import pytest

from sidekick_tools import query_store_data
from tests.conftest import make_client, ok_graphql_response


@pytest.mark.asyncio
async def test_query_returns_data_and_jit_instruction() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "X-Shopify-Access-Token" in request.headers
        return httpx.Response(
            200,
            json=ok_graphql_response({"orders": {"edges": [{"node": {"totalPrice": "12.00"}}]}}),
        )

    client = make_client(httpx.MockTransport(handler))
    try:
        result = await query_store_data(
            "{ orders(first: 1) { edges { node { totalPrice createdAt } } } }",
            client=client,
        )
    finally:
        await client.aclose()

    assert result.ok is True
    assert "orders" in result.data
    assert result.jit_instruction.startswith("[JIT:analytics_sales]")


@pytest.mark.asyncio
async def test_invalid_query_rejected_locally_without_http() -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={"data": {}})

    client = make_client(httpx.MockTransport(handler))
    try:
        result = await query_store_data("not a graphql query", client=client)
    finally:
        await client.aclose()

    assert called is False
    assert result.ok is False
    assert "GraphQL" in (result.error or "")


@pytest.mark.asyncio
async def test_graphql_errors_surface_with_jit_instruction() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "errors": [{"message": "Field 'foo' doesn't exist on type 'QueryRoot'"}],
                "extensions": {"cost": {"throttleStatus": {"currentlyAvailable": 900, "maximumAvailable": 1000, "restoreRate": 50}}},
            },
        )

    client = make_client(httpx.MockTransport(handler))
    try:
        result = await query_store_data("{ products(first: 1) { edges { node { descriptionHtml } } } }", client=client)
    finally:
        await client.aclose()

    assert result.ok is False
    assert "errors" in (result.error or "").lower() or "errors" in str(result.data).lower()
    assert result.jit_instruction.startswith("[JIT:content_creator]")
