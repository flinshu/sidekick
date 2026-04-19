"""批量给 dev store 造订单（通过 draftOrderCreate → draftOrderComplete）。

用法：
    uv run python scripts/seed_orders.py                 # 默认造 80 单
    uv run python scripts/seed_orders.py --count 30      # 造 30 单
    uv run python scripts/seed_orders.py --dry-run       # 只打印计划，不下单

注意：
- 只在 dev store 上跑！
- Shopify `createdAt` / `processedAt` 不能真正回溯，所以所有订单都会记录为"今天"。
  对"最近 30 天"类查询可用；"上周"查询可能在今天造完数据后的几天里逐渐有效。
- draftOrderComplete 以 paymentPending=false 标记为已支付，生成的订单 financialStatus=PAID。
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import random
import sys
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.progress import Progress

ROOT = Path(__file__).resolve().parent.parent
if (ROOT / ".env").exists():
    load_dotenv(ROOT / ".env")

from sidekick_tools import ShopifyClient, ShopifyError  # noqa: E402

console = Console()
logging.basicConfig(level=logging.WARNING)


GET_VARIANTS_QUERY = """
query GetVariants($cursor: String) {
  productVariants(first: 100, after: $cursor) {
    edges {
      cursor
      node {
        id
        title
        price
        sku
        inventoryQuantity
        product { id title status }
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""

DRAFT_ORDER_CREATE_MUTATION = """
mutation DraftCreate($input: DraftOrderInput!) {
  draftOrderCreate(input: $input) {
    draftOrder { id name totalPriceSet { shopMoney { amount currencyCode } } }
    userErrors { field message }
  }
}
"""

DRAFT_ORDER_COMPLETE_MUTATION = """
mutation DraftComplete($id: ID!) {
  draftOrderComplete(id: $id, paymentPending: false) {
    draftOrder { id order { id name totalPriceSet { shopMoney { amount } } } }
    userErrors { field message }
  }
}
"""


async def fetch_all_variants(client: ShopifyClient) -> list[dict]:
    all_variants: list[dict] = []
    cursor: str | None = None
    while True:
        resp = await client.graphql(GET_VARIANTS_QUERY, {"cursor": cursor})
        page = (resp.get("data") or {}).get("productVariants") or {}
        for edge in page.get("edges", []):
            node = edge["node"]
            if node["product"]["status"] == "ACTIVE":
                all_variants.append(node)
        if not page.get("pageInfo", {}).get("hasNextPage"):
            break
        cursor = page["pageInfo"]["endCursor"]
    return all_variants


async def create_one_order(
    client: ShopifyClient,
    variants: list[dict],
    rng: random.Random,
    *,
    customer_pool: list[str],
) -> tuple[bool, str]:
    # 1-3 个 line items，每个 variant 数量 1-3
    k = rng.randint(1, min(3, len(variants)))
    chosen = rng.sample(variants, k)
    line_items = [
        {
            "variantId": v["id"],
            "quantity": rng.randint(1, 3),
        }
        for v in chosen
    ]

    # 加权抽样：前 5 个客户消费频率高（形成 Top 消费客户），后面的尾部较低
    weights = [5.0 / (i + 1) for i in range(len(customer_pool))]
    email = rng.choices(customer_pool, weights=weights, k=1)[0]

    draft_input = {
        "lineItems": line_items,
        "useCustomerDefaultAddress": False,
        "email": email,
        "tags": ["seeded-by-sidekick-poc"],
    }

    try:
        resp = await client.graphql(DRAFT_ORDER_CREATE_MUTATION, {"input": draft_input})
    except ShopifyError as e:
        detail = f"{e} | errors={e.graphql_errors}" if e.graphql_errors else str(e)
        return False, f"draftOrderCreate 失败：{detail}"
    payload = (resp.get("data") or {}).get("draftOrderCreate") or {}
    errs = payload.get("userErrors") or []
    if errs:
        return False, f"draftOrderCreate userErrors: {errs}"
    draft = payload.get("draftOrder") or {}
    draft_id = draft.get("id")
    if not draft_id:
        return False, "draftOrderCreate 未返回 id"

    try:
        resp2 = await client.graphql(DRAFT_ORDER_COMPLETE_MUTATION, {"id": draft_id})
    except ShopifyError as e:
        return False, f"draftOrderComplete 失败：{e}"
    payload2 = (resp2.get("data") or {}).get("draftOrderComplete") or {}
    errs2 = payload2.get("userErrors") or []
    if errs2:
        return False, f"draftOrderComplete userErrors: {errs2}"
    order = (payload2.get("draftOrder") or {}).get("order") or {}
    return True, f"{order.get('name')} 总价 {order.get('totalPriceSet', {}).get('shopMoney', {}).get('amount')}"


async def main(count: int, dry_run: bool, seed: int, customers: int) -> int:
    rng = random.Random(seed)
    # 固定客户池：加权抽样让前几名成为高消费客户
    customer_pool = [f"sidekick-customer-{i:02d}@example.com" for i in range(customers)]
    async with ShopifyClient() as client:
        console.print("[dim]拉取 variant 列表...[/]")
        variants = await fetch_all_variants(client)
        console.print(f"获取到 [bold]{len(variants)}[/] 个 active variant")
        console.print(f"客户池：[bold]{len(customer_pool)}[/] 个（前几名会被加权为高消费客户）")
        if not variants:
            console.print("[red]没有可下单的 variant，先在 dev store 里建几个商品[/]")
            return 2

        if dry_run:
            console.print(f"[yellow]dry-run：将创建 {count} 个订单，每单 1-3 个 variant，来自 {len(variants)} 个候选[/]")
            for i in range(min(3, count)):
                sample = rng.sample(variants, min(2, len(variants)))
                weights = [5.0 / (j + 1) for j in range(len(customer_pool))]
                email = rng.choices(customer_pool, weights=weights, k=1)[0]
                console.print(f"  #{i+1}: 客户={email} 商品={[v['product']['title']+'/'+v['title'] for v in sample]}")
            return 0

        ok_count = 0
        fail_count = 0
        errors: list[str] = []
        with Progress() as progress:
            task = progress.add_task("造订单", total=count)
            for _ in range(count):
                ok, msg = await create_one_order(client, variants, rng, customer_pool=customer_pool)
                if ok:
                    ok_count += 1
                else:
                    fail_count += 1
                    errors.append(msg)
                progress.update(task, advance=1)

        console.print(f"\n[green]成功 {ok_count}[/] / [red]失败 {fail_count}[/]")
        if errors[:5]:
            console.print("[dim]前 5 条错误：[/]")
            for e in errors[:5]:
                console.print(f"  - {e}")
        return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=80, help="要造的订单数")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不真下单")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    parser.add_argument("--customers", type=int, default=15, help="客户池大小（前几名会被加权为高消费）")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.count, args.dry_run, args.seed, args.customers)))
