"""结构化输出 schemas：Agent 可以（可选地）把最终响应定型为这些 Pydantic 模型。

M1 不强制结构化输出（自由文本也行），但评估阶段常用来判"字段合理性"。
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class SalesReport(BaseModel):
    """销售分析报告。"""

    period: str = Field(description="分析的时间范围，例如 2024-W12 或 2024-03-01~2024-03-31")
    total_orders: int
    total_revenue: str = Field(description="如 '¥12,345.67'")
    top_products: list[dict] = Field(default_factory=list, description="Top 商品简单数组")
    decliners: list[dict] = Field(default_factory=list, description="销量下滑商品")
    notes: str | None = None


class InventoryAlert(BaseModel):
    """库存告警输出。"""

    alerts: list[dict] = Field(
        default_factory=list,
        description="每条含 product/variant/current_stock/suggested_restock/reasoning",
    )
    overstock: list[dict] = Field(
        default_factory=list,
        description="长期积压商品，每条含 product/variant/days_no_sales",
    )


class PromotionContent(BaseModel):
    """内容生成工具的 SEO + 描述输出。"""

    product_id: str
    title_suggestion: str | None = None
    description_html: str
    seo_title: str = Field(max_length=70)
    seo_description: str = Field(max_length=160)
    tags: list[str] = Field(default_factory=list)


# 用于 LLM-as-Judge 的 rubric 分数
class JudgeScore(BaseModel):
    overall: int = Field(ge=1, le=5)
    tool_selection_correct: bool
    jit_instruction_followed: bool
    graphql_syntax_valid: bool | None = None
    graphql_fields_reasonable: bool | None = None
    reasoning: str
