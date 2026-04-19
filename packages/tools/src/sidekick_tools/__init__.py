"""Sidekick Shopify MCP tools 公共入口。"""
from .jit_instructions import WRITE_OP_JIT, detect_scenario, jit_instruction_for
from .models import ConfirmDecision, ToolResult, WritePreview
from .query_store_data import query_store_data
from .schema_loader import assert_subset_within_budget, count_tokens, load_schema_subset
from .shopify_client import ShopifyClient, ShopifyCredentials, ShopifyError
from .write_tools import (
    create_automation,
    create_promotion,
    save_content,
    update_inventory,
    update_price,
)

__all__ = [
    # client & infra
    "ShopifyClient",
    "ShopifyCredentials",
    "ShopifyError",
    # schema
    "load_schema_subset",
    "count_tokens",
    "assert_subset_within_budget",
    # JIT
    "detect_scenario",
    "jit_instruction_for",
    "WRITE_OP_JIT",
    # models
    "ToolResult",
    "WritePreview",
    "ConfirmDecision",
    # tools
    "query_store_data",
    "update_price",
    "update_inventory",
    "save_content",
    "create_promotion",
    "create_automation",
]
