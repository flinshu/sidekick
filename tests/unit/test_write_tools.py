from __future__ import annotations

import httpx
import pytest

from sidekick_tools import create_automation, create_promotion, save_content, update_inventory, update_price
from tests.conftest import make_client, ok_graphql_response


def _handler_seq(*responses: httpx.Response) -> httpx.MockTransport:
    """逐个消费响应序列。"""
    seq = list(responses)

    def h(request: httpx.Request) -> httpx.Response:
        if not seq:
            return httpx.Response(500, text="no more responses")
        return seq.pop(0)

    return httpx.MockTransport(h)


# ========== update_price ==========


@pytest.mark.asyncio
async def test_update_price_phase1_returns_preview_and_token() -> None:
    mock = _handler_seq(
        httpx.Response(
            200,
            json=ok_graphql_response(
                {
                    "productVariant": {
                        "id": "gid://shopify/ProductVariant/1",
                        "title": "Default",
                        "sku": "SKU-1",
                        "price": "99.00",
                        "compareAtPrice": None,
                        "product": {"id": "gid://shopify/Product/1", "title": "Test"},
                    }
                }
            ),
        )
    )
    client = make_client(mock)
    try:
        result = await update_price(variant_id="gid://shopify/ProductVariant/1", new_price="79.00", client=client)
    finally:
        await client.aclose()

    assert result.ok is True
    assert result.requires_confirmation is True
    assert result.confirmation_token is not None
    assert result.preview is not None
    assert "79.00" in result.preview["summary"]


@pytest.mark.asyncio
async def test_update_price_phase2_executes_mutation() -> None:
    # phase 2：先反查 productId（bulk 接口要求），再打 mutation
    mock = _handler_seq(
        httpx.Response(
            200,
            json=ok_graphql_response(
                {
                    "productVariant": {
                        "id": "gid://shopify/ProductVariant/1",
                        "title": "Default",
                        "sku": None,
                        "price": "99.00",
                        "compareAtPrice": None,
                        "product": {"id": "gid://shopify/Product/1", "title": "T"},
                    }
                }
            ),
        ),
        httpx.Response(
            200,
            json=ok_graphql_response(
                {
                    "productVariantsBulkUpdate": {
                        "productVariants": [
                            {
                                "id": "gid://shopify/ProductVariant/1",
                                "price": "79.00",
                                "compareAtPrice": None,
                            }
                        ],
                        "userErrors": [],
                    }
                }
            ),
        ),
    )
    client = make_client(mock)
    try:
        result = await update_price(
            variant_id="gid://shopify/ProductVariant/1",
            new_price="79.00",
            confirmed_token="TOKEN",
            confirmation_token="TOKEN",
            client=client,
        )
    finally:
        await client.aclose()

    assert result.ok is True
    assert result.requires_confirmation is False
    assert result.data["productVariants"][0]["price"] == "79.00"


@pytest.mark.asyncio
async def test_update_price_mismatched_token_aborts() -> None:
    mock = _handler_seq()  # 不应有请求
    client = make_client(mock)
    try:
        result = await update_price(
            variant_id="gid://x",
            new_price="1.00",
            confirmed_token="WRONG",
            confirmation_token="RIGHT",
            client=client,
        )
    finally:
        await client.aclose()

    assert result.ok is False
    assert "token" in (result.error or "").lower()


# ========== update_inventory ==========


@pytest.mark.asyncio
async def test_update_inventory_preview_has_delta_summary() -> None:
    mock = _handler_seq(
        httpx.Response(
            200,
            json=ok_graphql_response(
                {
                    "inventoryItem": {
                        "id": "gid://shopify/InventoryItem/1",
                        "sku": "SKU-1",
                        "variant": {"id": "gid://shopify/ProductVariant/1", "title": "Default", "product": {"title": "Widget"}},
                        "inventoryLevels": {
                            "edges": [
                                {
                                    "node": {
                                        "id": "gid://shopify/InventoryLevel/1",
                                        "location": {"id": "gid://shopify/Location/1", "name": "Warehouse"},
                                        "quantities": [{"name": "available", "quantity": 10}],
                                    }
                                }
                            ]
                        },
                    }
                }
            ),
        )
    )
    client = make_client(mock)
    try:
        result = await update_inventory(
            inventory_item_id="gid://shopify/InventoryItem/1",
            location_id="gid://shopify/Location/1",
            delta=5,
            client=client,
        )
    finally:
        await client.aclose()

    assert result.ok is True
    assert result.requires_confirmation is True
    assert "+5" in result.preview["summary"]
    assert result.preview["after"]["available"] == 15


# ========== save_content ==========


@pytest.mark.asyncio
async def test_save_content_rejects_long_seo_description() -> None:
    client = make_client(_handler_seq())  # 无请求也 ok
    try:
        result = await save_content(
            product_id="gid://x",
            seo_description="x" * 200,  # 超过 160 字符
            client=client,
        )
    finally:
        await client.aclose()

    assert result.ok is False
    assert "160" in (result.error or "")


@pytest.mark.asyncio
async def test_save_content_phase1_returns_preview() -> None:
    mock = _handler_seq(
        httpx.Response(
            200,
            json=ok_graphql_response(
                {
                    "product": {
                        "id": "gid://shopify/Product/1",
                        "title": "Widget",
                        "descriptionHtml": "<p>old</p>",
                        "seo": {"title": "old title", "description": "old desc"},
                        "tags": ["tag1"],
                    }
                }
            ),
        )
    )
    client = make_client(mock)
    try:
        result = await save_content(
            product_id="gid://shopify/Product/1",
            description_html="<p>new description</p>",
            seo_description="new seo description within limit",
            client=client,
        )
    finally:
        await client.aclose()

    assert result.ok is True
    assert result.requires_confirmation is True
    assert result.preview is not None


# ========== create_promotion ==========


@pytest.mark.asyncio
async def test_create_promotion_validates_percentage_range() -> None:
    result_over = await create_promotion(title="T", discount_code="X", percentage_off=120)
    assert result_over.ok is False

    result_neg = await create_promotion(title="T", discount_code="X", percentage_off=-5)
    assert result_neg.ok is False


@pytest.mark.asyncio
async def test_create_promotion_phase1_returns_preview_without_api_call() -> None:
    mock = _handler_seq()  # 不应有请求
    client = make_client(mock)
    try:
        result = await create_promotion(
            title="春季大促",
            discount_code="SPRING20",
            percentage_off=20,
            client=client,
        )
    finally:
        await client.aclose()

    assert result.ok is True
    assert result.requires_confirmation is True
    assert "SPRING20" in result.preview["summary"]


# ========== create_automation ==========


@pytest.mark.asyncio
async def test_create_automation_is_stub_in_m1() -> None:
    result = await create_automation(name="restock-alert", trigger="low_stock", actions=[])
    assert result.ok is False
    assert "M1" in (result.error or "") or "M2" in (result.error or "")
