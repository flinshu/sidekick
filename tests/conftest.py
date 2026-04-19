"""pytest 公共 fixture：mock Shopify 凭证 + client。"""
from __future__ import annotations

import os
from typing import Any

import httpx
import pytest

from sidekick_tools import ShopifyClient, ShopifyCredentials


@pytest.fixture(autouse=True)
def _mock_shopify_env(monkeypatch):
    monkeypatch.setenv("SHOPIFY_SHOP_DOMAIN", "test-store.myshopify.com")
    monkeypatch.setenv("SHOPIFY_ADMIN_TOKEN", "shpat_test_token")
    monkeypatch.setenv("SHOPIFY_API_VERSION", "2025-04")


def make_client(handler: httpx.MockTransport) -> ShopifyClient:
    """用 MockTransport 构造 ShopifyClient，不会打真实网络。"""
    creds = ShopifyCredentials(
        shop_domain="test-store.myshopify.com",
        admin_token="shpat_test_token",
        api_version="2025-04",
    )
    async_client = httpx.AsyncClient(transport=handler)
    return ShopifyClient(credentials=creds, client=async_client)


def ok_graphql_response(data: dict[str, Any], *, throttle: dict[str, float] | None = None) -> dict[str, Any]:
    """构造一个带 extensions.cost.throttleStatus 的 GraphQL 200 响应。"""
    throttle = throttle or {"currentlyAvailable": 900, "maximumAvailable": 1000, "restoreRate": 50}
    return {
        "data": data,
        "extensions": {
            "cost": {
                "requestedQueryCost": 10,
                "actualQueryCost": 8,
                "throttleStatus": throttle,
            }
        },
    }
