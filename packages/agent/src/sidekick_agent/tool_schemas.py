"""把 sidekick_tools 的 async 工具函数转成 OpenAI/Anthropic tool-calling 协议可接受的 schema。

LiteLLM 用 OpenAI 的 tool schema 格式，所有后端（OpenAI/Anthropic/DashScope）都会把它
翻译成各自的 tool-calling 协议。所以我们只要写一份 OpenAI 风格的 schema。
"""
from __future__ import annotations

from typing import Any


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "query_store_data",
            "description": (
                "对 Shopify Admin GraphQL API 执行只读查询。适用于一切数据获取：销售、"
                "订单、商品、库存、客户、促销等。只允许用 system prompt 中给出的 schema 子集。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "完整的 GraphQL 查询字符串（以 '{' 开头的 query 文档）",
                    },
                    "variables": {
                        "type": "object",
                        "description": "可选的 GraphQL 变量对象",
                        "additionalProperties": True,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_price",
            "description": (
                "更新某个 ProductVariant 的价格。两阶段调用：第一次不带 confirmed_token 返回 preview，"
                "得到商家确认后再带上 confirmed_token=confirmation_token 调一次真正执行。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "variant_id": {"type": "string", "description": "GraphQL global ID"},
                    "new_price": {"type": "string", "description": '新价格，字符串格式如 "79.00"'},
                    "confirmed_token": {
                        "type": "string",
                        "description": "商家确认后把 preview 返回的 confirmation_token 原样回传；未确认时不传",
                    },
                    "confirmation_token": {
                        "type": "string",
                        "description": "与 confirmed_token 配对校验，未确认时不传",
                    },
                },
                "required": ["variant_id", "new_price"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_inventory",
            "description": "调整库存数量（delta 正负均可）。两阶段：先预览，用户确认后执行。",
            "parameters": {
                "type": "object",
                "properties": {
                    "inventory_item_id": {"type": "string"},
                    "location_id": {"type": "string"},
                    "delta": {"type": "integer"},
                    "reason": {"type": "string", "description": '默认 "correction"'},
                    "confirmed_token": {"type": "string"},
                    "confirmation_token": {"type": "string"},
                },
                "required": ["inventory_item_id", "location_id", "delta"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_content",
            "description": (
                "更新商品描述/SEO/tags。SEO description ≤ 160 字符。两阶段：先预览，确认后执行。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string"},
                    "description_html": {"type": "string"},
                    "seo_title": {"type": "string"},
                    "seo_description": {"type": "string", "description": "不超过 160 字符"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "confirmed_token": {"type": "string"},
                    "confirmation_token": {"type": "string"},
                },
                "required": ["product_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_promotion",
            "description": "创建促销（PriceRule + DiscountCode）。两阶段：先预览，确认后执行。",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "discount_code": {"type": "string", "description": "结账时使用的折扣码"},
                    "percentage_off": {
                        "type": "number",
                        "description": "折扣百分比（正数，0-90）",
                    },
                    "starts_at": {"type": "string", "description": "ISO 8601 开始时间"},
                    "ends_at": {"type": "string", "description": "ISO 8601 结束时间（可选）"},
                    "confirmed_token": {"type": "string"},
                    "confirmation_token": {"type": "string"},
                },
                "required": ["title", "discount_code", "percentage_off"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_automation",
            "description": "M1 尚未实现（Shopify Flow API 接入留到 M2）。调用会得到未实现错误。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "trigger": {"type": "string"},
                    "actions": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["name", "trigger", "actions"],
            },
        },
    },
]


TOOL_NAMES: list[str] = [s["function"]["name"] for s in TOOL_SCHEMAS]
