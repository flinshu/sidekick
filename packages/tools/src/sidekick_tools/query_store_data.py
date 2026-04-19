"""query_store_data：统一 GraphQL 读工具。"""
from __future__ import annotations

import re
from typing import Any

from .jit_instructions import jit_instruction_for
from .models import ToolResult
from .shopify_client import ShopifyClient, ShopifyError

GRAPHQL_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _looks_like_graphql(query: str) -> bool:
    """非常宽松的语法预检：找到至少一对花括号且没有明显非法字符。"""
    if not query or not isinstance(query, str):
        return False
    text = query.strip()
    if "{" not in text or "}" not in text:
        return False
    if text.count("{") != text.count("}"):
        return False
    return True


async def query_store_data(
    query: str,
    *,
    variables: dict[str, Any] | None = None,
    client: ShopifyClient | None = None,
) -> ToolResult:
    """对 Shopify Admin GraphQL 执行查询。

    Args:
        query: GraphQL 查询字符串（Agent 自己生成）。
        variables: 可选变量。
        client: 可注入的 ShopifyClient（测试时使用）。

    Returns:
        ToolResult: data 含 Shopify 返回的 data 段；jit_instruction 按查询场景附带。
    """
    if not _looks_like_graphql(query):
        return ToolResult(
            ok=False,
            error="GraphQL 语法错误：query 必须包含成对花括号且非空",
            jit_instruction=jit_instruction_for(query or ""),
        )

    owns_client = client is None
    client = client or ShopifyClient()
    try:
        try:
            payload = await client.graphql(query, variables)
        except ShopifyError as e:
            return ToolResult(
                ok=False,
                error=str(e),
                data={"graphql_errors": e.graphql_errors} if e.graphql_errors else {},
                jit_instruction=jit_instruction_for(query),
            )
        return ToolResult(
            ok=True,
            data=payload.get("data") or {},
            jit_instruction=jit_instruction_for(query),
        )
    finally:
        if owns_client:
            await client.aclose()
