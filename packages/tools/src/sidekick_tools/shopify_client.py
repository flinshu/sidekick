"""Shopify Admin API 客户端：GraphQL + rate limit 退避。"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30.0
RATE_LIMIT_THRESHOLD_RATIO = 0.10  # 余量低于 10% 时触发退避
RATE_LIMIT_RECOVERY_BUDGET = 50  # 等到余量回到至少 50 才继续


@dataclass(frozen=True)
class ShopifyCredentials:
    shop_domain: str
    admin_token: str
    api_version: str = "2025-10"

    @classmethod
    def from_env(cls) -> "ShopifyCredentials":
        domain = os.environ.get("SHOPIFY_SHOP_DOMAIN", "").strip()
        token = os.environ.get("SHOPIFY_ADMIN_TOKEN", "").strip()
        version = os.environ.get("SHOPIFY_API_VERSION", "2025-10").strip()
        if not domain or not token:
            raise RuntimeError(
                "缺少 Shopify 凭证。请设置 SHOPIFY_SHOP_DOMAIN 和 SHOPIFY_ADMIN_TOKEN。"
            )
        return cls(shop_domain=domain, admin_token=token, api_version=version)

    def graphql_url(self) -> str:
        return f"https://{self.shop_domain}/admin/api/{self.api_version}/graphql.json"

    def headers(self) -> dict[str, str]:
        return {
            "X-Shopify-Access-Token": self.admin_token,
            "Content-Type": "application/json",
        }


class ShopifyError(RuntimeError):
    """对调用方抛出的 Shopify 异常。包含 HTTP / GraphQL 错误细节。

    str(e) 会同时包含 graphql_errors 摘要，方便日志/trace 直接看到根因（例如缺 scope）。
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        graphql_errors: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.graphql_errors = graphql_errors or []
        self._base_message = message

    def __str__(self) -> str:
        if not self.graphql_errors:
            return self._base_message
        # 摘取每条 error 的 message + 缺失 scope 提示
        summaries: list[str] = []
        for ge in self.graphql_errors:
            msg = ge.get("message", "")
            req = (ge.get("extensions") or {}).get("requiredAccess")
            if req:
                summaries.append(f"{msg} [requires: {req}]")
            else:
                summaries.append(msg)
        return f"{self._base_message}: {' | '.join(summaries)}"


class ShopifyClient:
    """异步 Shopify GraphQL 客户端，带 rate-limit 自动退避。"""

    def __init__(
        self,
        credentials: ShopifyCredentials | None = None,
        *,
        client: httpx.AsyncClient | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.credentials = credentials or ShopifyCredentials.from_env()
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout)
        # 最近一次响应观察到的 throttle 余量（None 表示未知）
        self._last_currently_available: float | None = None
        self._last_max_available: float | None = None
        self._last_restore_rate: float | None = None  # 每秒恢复多少

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> "ShopifyClient":
        return self

    async def __aexit__(self, *_args: Any) -> None:
        await self.aclose()

    async def graphql(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        await self._maybe_backoff()
        try:
            resp = await self._client.post(
                self.credentials.graphql_url(),
                json={"query": query, "variables": variables or {}},
                headers=self.credentials.headers(),
            )
        except httpx.HTTPError as e:
            raise ShopifyError(f"HTTP 调用失败：{e}") from e

        if resp.status_code >= 500:
            raise ShopifyError(
                f"Shopify {resp.status_code} 服务端错误", status_code=resp.status_code
            )
        if resp.status_code == 429:
            # rate limit hit; 重试一次
            retry_after = float(resp.headers.get("Retry-After", "2"))
            logger.warning("Shopify 限流 429，等待 %.1fs 后重试", retry_after)
            await asyncio.sleep(retry_after)
            return await self.graphql(query, variables)

        try:
            payload = resp.json()
        except Exception as e:
            raise ShopifyError(
                f"无法解析响应 JSON：{e}", status_code=resp.status_code
            ) from e

        self._record_throttle(payload)

        if resp.status_code != 200:
            raise ShopifyError(
                f"Shopify HTTP {resp.status_code}：{resp.text[:200]}",
                status_code=resp.status_code,
            )

        if "errors" in payload and payload["errors"]:
            raise ShopifyError(
                "Shopify GraphQL errors", graphql_errors=payload["errors"]
            )

        return payload

    def _record_throttle(self, payload: dict[str, Any]) -> None:
        ext = (payload or {}).get("extensions") or {}
        cost = ext.get("cost") or {}
        throttle = cost.get("throttleStatus") or {}
        ca = throttle.get("currentlyAvailable")
        ma = throttle.get("maximumAvailable")
        rr = throttle.get("restoreRate")
        if isinstance(ca, (int, float)):
            self._last_currently_available = float(ca)
        if isinstance(ma, (int, float)):
            self._last_max_available = float(ma)
        if isinstance(rr, (int, float)):
            self._last_restore_rate = float(rr)

    async def _maybe_backoff(self) -> None:
        ca = self._last_currently_available
        ma = self._last_max_available
        rr = self._last_restore_rate
        if ca is None or ma is None or ma <= 0:
            return
        if ca >= ma * RATE_LIMIT_THRESHOLD_RATIO:
            return
        # 余量低于阈值，等到至少恢复到 RECOVERY_BUDGET
        deficit = max(RATE_LIMIT_RECOVERY_BUDGET - ca, 1)
        sleep_s = deficit / (rr or 50.0)
        sleep_s = max(0.2, min(sleep_s, 5.0))
        logger.info(
            "Shopify rate-limit 退避：余量 %.0f / %.0f，等待 %.2fs",
            ca,
            ma,
            sleep_s,
        )
        await asyncio.sleep(sleep_s)

    @property
    def last_throttle(self) -> dict[str, float | None]:
        return {
            "currentlyAvailable": self._last_currently_available,
            "maximumAvailable": self._last_max_available,
            "restoreRate": self._last_restore_rate,
        }


def utc_now() -> float:
    return time.time()
