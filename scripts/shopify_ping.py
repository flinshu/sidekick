"""
Shopify API 连通性测试脚本。

用法：
    uv run python scripts/shopify_ping.py

会读取环境变量：
    SHOPIFY_SHOP_DOMAIN   例如 my-store.myshopify.com
    SHOPIFY_ADMIN_TOKEN   shpat_ 开头
    SHOPIFY_API_VERSION   默认 2025-04

输出：
    - shop 基本信息（名字、domain、货币）
    - 商品总数
    - 订单总数
    - rate limit 当前余量
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv  # type: ignore[import-not-found]


def load_env() -> None:
    root = Path(__file__).resolve().parent.parent
    env_path = root / ".env"
    if env_path.exists():
        load_dotenv(env_path)


QUERY = """
{
  shop {
    name
    myshopifyDomain
    currencyCode
    primaryDomain { host }
  }
  productsCount: products(first: 1) {
    pageInfo { hasNextPage }
  }
  ordersCount: orders(first: 1) {
    pageInfo { hasNextPage }
  }
}
"""


def main() -> int:
    load_env()
    domain = os.getenv("SHOPIFY_SHOP_DOMAIN")
    token = os.getenv("SHOPIFY_ADMIN_TOKEN")
    api_version = os.getenv("SHOPIFY_API_VERSION", "2025-10")

    missing: list[str] = []
    if not domain or domain.startswith("your-"):
        missing.append("SHOPIFY_SHOP_DOMAIN")
    if not token or token.startswith("shpat_xxxx"):
        missing.append("SHOPIFY_ADMIN_TOKEN")
    if missing:
        print(f"[ERROR] 缺少环境变量：{', '.join(missing)}")
        print("请在 .env 中填入真实的 Shopify dev store 配置。")
        return 2

    url = f"https://{domain}/admin/api/{api_version}/graphql.json"
    headers = {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json",
    }

    print(f"[INFO] 连接 {url} ...")
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(url, json={"query": QUERY}, headers=headers)
    except httpx.HTTPError as e:
        print(f"[ERROR] HTTP 调用失败：{e}")
        return 3

    if resp.status_code != 200:
        print(f"[ERROR] HTTP {resp.status_code}")
        print(resp.text[:500])
        return 4

    payload = resp.json()
    if "errors" in payload:
        print("[ERROR] GraphQL 返回 errors：")
        print(payload["errors"])
        return 5

    shop = payload["data"]["shop"]
    cost = payload.get("extensions", {}).get("cost", {}).get("throttleStatus", {})

    print("\n=== Shopify 连通性 OK ===")
    print(f"店铺名: {shop['name']}")
    print(f"myshopify 域名: {shop['myshopifyDomain']}")
    print(f"主域名: {shop['primaryDomain']['host']}")
    print(f"货币: {shop['currencyCode']}")
    print(f"有商品: {payload['data']['productsCount']['pageInfo']['hasNextPage']}")
    print(f"有订单: {payload['data']['ordersCount']['pageInfo']['hasNextPage']}")
    if cost:
        avail = cost.get("currentlyAvailable")
        total = cost.get("maximumAvailable")
        print(f"GraphQL 速率余量: {avail}/{total}")
    print("API version:", api_version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
