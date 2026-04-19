"""5 个 Shopify 写工具：先返回 preview + requires_confirmation，确认后真正执行。"""
from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any

from .jit_instructions import WRITE_OP_JIT
from .models import ToolResult, WritePreview
from .shopify_client import ShopifyClient, ShopifyError


def _confirmation_token() -> str:
    return secrets.token_urlsafe(12)


async def _execute_mutation(
    client: ShopifyClient,
    query: str,
    variables: dict[str, Any],
    *,
    payload_key: str,
) -> ToolResult:
    try:
        resp = await client.graphql(query, variables)
    except ShopifyError as e:
        return ToolResult(
            ok=False,
            error=str(e),
            jit_instruction=WRITE_OP_JIT,
            data={"graphql_errors": e.graphql_errors} if e.graphql_errors else {},
        )
    payload = (resp.get("data") or {}).get(payload_key) or {}
    user_errors = payload.get("userErrors") or []
    if user_errors:
        return ToolResult(
            ok=False,
            error=f"Shopify userErrors: {user_errors}",
            jit_instruction=WRITE_OP_JIT,
            data={"userErrors": user_errors},
        )
    return ToolResult(
        ok=True,
        data=payload,
        jit_instruction=WRITE_OP_JIT,
    )


# ===== update_price =====

GET_VARIANT_QUERY = """
query GetVariant($id: ID!) {
  productVariant(id: $id) {
    id title sku price compareAtPrice
    product { id title }
  }
}
"""

# Shopify 2024-04+ 移除了 productVariantUpdate，统一走 bulk 接口
UPDATE_VARIANT_PRICE_MUTATION = """
mutation BulkUpdatePrice($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
  productVariantsBulkUpdate(productId: $productId, variants: $variants) {
    productVariants { id price compareAtPrice }
    userErrors { field message }
  }
}
"""


async def update_price(
    variant_id: str,
    new_price: str,
    *,
    confirmed_token: str | None = None,
    confirmation_token: str | None = None,
    client: ShopifyClient | None = None,
) -> ToolResult:
    """更新某 variant 的价格。

    第一次调用（confirmed_token=None）：返回 preview + confirmation_token，要求用户确认。
    第二次调用（confirmed_token == confirmation_token）：执行 mutation。
    """
    owns_client = client is None
    client = client or ShopifyClient()
    try:
        # Phase 1: preview
        if not confirmed_token:
            try:
                resp = await client.graphql(GET_VARIANT_QUERY, {"id": variant_id})
            except ShopifyError as e:
                return ToolResult(ok=False, error=str(e), jit_instruction=WRITE_OP_JIT)
            variant = (resp.get("data") or {}).get("productVariant")
            if not variant:
                return ToolResult(
                    ok=False,
                    error=f"找不到 variant {variant_id}",
                    jit_instruction=WRITE_OP_JIT,
                )
            token = _confirmation_token()
            preview = WritePreview(
                operation="update_price",
                summary=f"调整 variant {variant['title']} 价格：{variant['price']} → {new_price}",
                before={"price": variant["price"], "compareAtPrice": variant.get("compareAtPrice")},
                after={"price": new_price, "compareAtPrice": variant.get("compareAtPrice")},
                impact=f"商品「{variant['product']['title']}」的此 variant 立即生效",
            )
            return ToolResult(
                ok=True,
                jit_instruction=WRITE_OP_JIT,
                requires_confirmation=True,
                confirmation_token=token,
                preview=preview.model_dump(),
                data={"variant_id": variant_id, "new_price": new_price},
            )

        # Phase 2: actually execute
        if confirmation_token and confirmed_token != confirmation_token:
            return ToolResult(
                ok=False,
                error="确认 token 不匹配，操作已取消",
                jit_instruction=WRITE_OP_JIT,
            )
        # bulk 接口要 productId，从 variant 反查
        try:
            v_resp = await client.graphql(GET_VARIANT_QUERY, {"id": variant_id})
        except ShopifyError as e:
            return ToolResult(ok=False, error=str(e), jit_instruction=WRITE_OP_JIT)
        variant = (v_resp.get("data") or {}).get("productVariant")
        if not variant:
            return ToolResult(
                ok=False,
                error=f"找不到 variant {variant_id}",
                jit_instruction=WRITE_OP_JIT,
            )
        product_id = variant["product"]["id"]
        return await _execute_mutation(
            client,
            UPDATE_VARIANT_PRICE_MUTATION,
            {
                "productId": product_id,
                "variants": [{"id": variant_id, "price": new_price}],
            },
            payload_key="productVariantsBulkUpdate",
        )
    finally:
        if owns_client:
            await client.aclose()


# ===== update_inventory =====

INVENTORY_ADJUST_MUTATION = """
mutation Adjust($input: InventoryAdjustQuantitiesInput!) {
  inventoryAdjustQuantities(input: $input) {
    inventoryAdjustmentGroup { id }
    userErrors { field message }
  }
}
"""

GET_INVENTORY_QUERY = """
query InvLevel($id: ID!) {
  inventoryItem(id: $id) {
    id sku
    variant { id title product { title } }
    inventoryLevels(first: 5) {
      edges { node { id location { id name } quantities(names: ["available"]) { name quantity } } }
    }
  }
}
"""


async def update_inventory(
    inventory_item_id: str,
    location_id: str,
    delta: int,
    reason: str = "correction",
    *,
    confirmed_token: str | None = None,
    confirmation_token: str | None = None,
    client: ShopifyClient | None = None,
) -> ToolResult:
    owns_client = client is None
    client = client or ShopifyClient()
    try:
        if not confirmed_token:
            try:
                resp = await client.graphql(GET_INVENTORY_QUERY, {"id": inventory_item_id})
            except ShopifyError as e:
                return ToolResult(ok=False, error=str(e), jit_instruction=WRITE_OP_JIT)
            item = (resp.get("data") or {}).get("inventoryItem")
            if not item:
                return ToolResult(
                    ok=False,
                    error=f"找不到 inventoryItem {inventory_item_id}",
                    jit_instruction=WRITE_OP_JIT,
                )
            current_avail: int | None = None
            for edge in item.get("inventoryLevels", {}).get("edges", []):
                node = edge["node"]
                if node["location"]["id"] == location_id:
                    quantities = node.get("quantities") or []
                    for q in quantities:
                        if q["name"] == "available":
                            current_avail = q["quantity"]
            token = _confirmation_token()
            preview = WritePreview(
                operation="update_inventory",
                summary=(
                    f"{item['variant']['product']['title']} - {item['variant']['title']}: "
                    f"{'+' if delta >= 0 else ''}{delta}（原 {current_avail}, 新 {(current_avail or 0) + delta}）"
                ),
                before={"available": current_avail},
                after={"available": (current_avail or 0) + delta},
                impact=f"location={location_id}, 原因={reason}",
            )
            return ToolResult(
                ok=True,
                jit_instruction=WRITE_OP_JIT,
                requires_confirmation=True,
                confirmation_token=token,
                preview=preview.model_dump(),
                data={
                    "inventory_item_id": inventory_item_id,
                    "location_id": location_id,
                    "delta": delta,
                    "reason": reason,
                },
            )
        if confirmation_token and confirmed_token != confirmation_token:
            return ToolResult(
                ok=False, error="确认 token 不匹配", jit_instruction=WRITE_OP_JIT
            )
        variables = {
            "input": {
                "reason": reason,
                "name": "available",
                "changes": [
                    {
                        "delta": delta,
                        "inventoryItemId": inventory_item_id,
                        "locationId": location_id,
                    }
                ],
            }
        }
        return await _execute_mutation(
            client, INVENTORY_ADJUST_MUTATION, variables, payload_key="inventoryAdjustQuantities"
        )
    finally:
        if owns_client:
            await client.aclose()


# ===== save_content =====

GET_PRODUCT_BASIC_QUERY = """
query GetProduct($id: ID!) {
  product(id: $id) {
    id title descriptionHtml seo { title description } tags
  }
}
"""

PRODUCT_UPDATE_MUTATION = """
mutation UpdateProduct($input: ProductInput!) {
  productUpdate(input: $input) {
    product { id title seo { title description } }
    userErrors { field message }
  }
}
"""

SEO_DESCRIPTION_LIMIT = 160


async def save_content(
    product_id: str,
    *,
    description_html: str | None = None,
    seo_title: str | None = None,
    seo_description: str | None = None,
    tags: list[str] | None = None,
    confirmed_token: str | None = None,
    confirmation_token: str | None = None,
    client: ShopifyClient | None = None,
) -> ToolResult:
    if seo_description and len(seo_description) > SEO_DESCRIPTION_LIMIT:
        return ToolResult(
            ok=False,
            error=f"SEO description 超过 {SEO_DESCRIPTION_LIMIT} 字符（当前 {len(seo_description)}）",
            jit_instruction=WRITE_OP_JIT,
        )
    owns_client = client is None
    client = client or ShopifyClient()
    try:
        if not confirmed_token:
            try:
                resp = await client.graphql(GET_PRODUCT_BASIC_QUERY, {"id": product_id})
            except ShopifyError as e:
                return ToolResult(ok=False, error=str(e), jit_instruction=WRITE_OP_JIT)
            product = (resp.get("data") or {}).get("product")
            if not product:
                return ToolResult(
                    ok=False,
                    error=f"找不到 product {product_id}",
                    jit_instruction=WRITE_OP_JIT,
                )
            token = _confirmation_token()
            preview = WritePreview(
                operation="save_content",
                summary=f"更新商品「{product['title']}」的描述/SEO/tags",
                before={
                    "descriptionHtml": (product.get("descriptionHtml") or "")[:200],
                    "seo": product.get("seo"),
                    "tags": product.get("tags"),
                },
                after={
                    "descriptionHtml": (description_html or product.get("descriptionHtml") or "")[:200],
                    "seo": {
                        "title": seo_title or (product.get("seo") or {}).get("title"),
                        "description": seo_description or (product.get("seo") or {}).get("description"),
                    },
                    "tags": tags if tags is not None else product.get("tags"),
                },
                impact=f"修改后立即对买家可见。SEO 描述长度：{len(seo_description or '')} 字符",
            )
            return ToolResult(
                ok=True,
                jit_instruction=WRITE_OP_JIT,
                requires_confirmation=True,
                confirmation_token=token,
                preview=preview.model_dump(),
                data={
                    "product_id": product_id,
                    "description_html": description_html,
                    "seo_title": seo_title,
                    "seo_description": seo_description,
                    "tags": tags,
                },
            )
        if confirmation_token and confirmed_token != confirmation_token:
            return ToolResult(ok=False, error="确认 token 不匹配", jit_instruction=WRITE_OP_JIT)
        product_input: dict[str, Any] = {"id": product_id}
        if description_html is not None:
            product_input["descriptionHtml"] = description_html
        if seo_title is not None or seo_description is not None:
            product_input["seo"] = {
                k: v
                for k, v in {"title": seo_title, "description": seo_description}.items()
                if v is not None
            }
        if tags is not None:
            product_input["tags"] = tags
        return await _execute_mutation(
            client, PRODUCT_UPDATE_MUTATION, {"input": product_input}, payload_key="productUpdate"
        )
    finally:
        if owns_client:
            await client.aclose()


# ===== create_promotion =====

# Shopify 2024-01+ 起 priceRuleCreate / discountCodeCreate 已下线，
# 统一走新 Discounts API：discountCodeBasicCreate（单 mutation 同时建规则 + code）
DISCOUNT_CODE_BASIC_CREATE_MUTATION = """
mutation DiscountCodeBasicCreate($basicCodeDiscount: DiscountCodeBasicInput!) {
  discountCodeBasicCreate(basicCodeDiscount: $basicCodeDiscount) {
    codeDiscountNode {
      id
      codeDiscount {
        ... on DiscountCodeBasic {
          title
          status
          codes(first: 1) { nodes { code } }
        }
      }
    }
    userErrors { field message }
  }
}
"""


async def create_promotion(
    title: str,
    discount_code: str,
    percentage_off: float,
    *,
    starts_at: str | None = None,  # ISO 8601
    ends_at: str | None = None,
    confirmed_token: str | None = None,
    confirmation_token: str | None = None,
    client: ShopifyClient | None = None,
) -> ToolResult:
    if percentage_off <= 0 or percentage_off > 90:
        return ToolResult(
            ok=False,
            error="百分比折扣必须在 0-90 之间",
            jit_instruction=WRITE_OP_JIT,
        )
    starts_at = starts_at or datetime.utcnow().isoformat() + "Z"
    owns_client = client is None
    client = client or ShopifyClient()
    try:
        if not confirmed_token:
            token = _confirmation_token()
            preview = WritePreview(
                operation="create_promotion",
                summary=f"创建促销「{title}」+ 折扣码 {discount_code}（{percentage_off}% off）",
                after={
                    "title": title,
                    "code": discount_code,
                    "percentage_off": percentage_off,
                    "starts_at": starts_at,
                    "ends_at": ends_at,
                },
                impact="折扣码立即生效，所有商家可在结账时使用",
            )
            return ToolResult(
                ok=True,
                jit_instruction=WRITE_OP_JIT,
                requires_confirmation=True,
                confirmation_token=token,
                preview=preview.model_dump(),
                data={
                    "title": title,
                    "discount_code": discount_code,
                    "percentage_off": percentage_off,
                    "starts_at": starts_at,
                    "ends_at": ends_at,
                },
            )
        if confirmation_token and confirmed_token != confirmation_token:
            return ToolResult(ok=False, error="确认 token 不匹配", jit_instruction=WRITE_OP_JIT)
        basic_input: dict[str, Any] = {
            "title": title,
            "code": discount_code,
            "startsAt": starts_at,
            "customerSelection": {"all": True},
            "customerGets": {
                "items": {"all": True},
                "value": {"percentage": abs(percentage_off) / 100.0},
            },
            "appliesOncePerCustomer": False,
        }
        if ends_at:
            basic_input["endsAt"] = ends_at
        return await _execute_mutation(
            client,
            DISCOUNT_CODE_BASIC_CREATE_MUTATION,
            {"basicCodeDiscount": basic_input},
            payload_key="discountCodeBasicCreate",
        )
    finally:
        if owns_client:
            await client.aclose()


# ===== create_automation (M1 stub) =====


async def create_automation(
    name: str,
    trigger: str,
    actions: list[dict[str, Any]],
    *,
    confirmed_token: str | None = None,
    confirmation_token: str | None = None,
    client: ShopifyClient | None = None,
) -> ToolResult:
    """M1 stub：Shopify Flow API 接入留到 M2。

    返回一个明确的"未实现"信号，让 Agent 知道该任务暂不可执行。
    """
    return ToolResult(
        ok=False,
        error="create_automation 在 M1 尚未实现（Shopify Flow API 接入留到 M2）",
        jit_instruction=WRITE_OP_JIT,
        requires_confirmation=False,
        data={"name": name, "trigger": trigger, "actions": actions},
    )
