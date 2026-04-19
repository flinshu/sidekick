"""JIT 指令规则：根据 GraphQL 查询内容识别场景，附带对应指令。

设计原则：
- 系统提示词稳定（只放通用 Agent 行为定义），prompt cache 才能命中
- 场景化指引通过工具返回值动态注入
- 可按 beta flag、模型版本、场景上下文调整（暂不实现，预留接口）

参考：Shopify Engineering, Building Production-Ready Agentic Systems (ICML 2025)
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class JitRule:
    name: str
    keywords: tuple[str, ...]
    instruction: str


# 关键字按场景匹配（不区分大小写）。匹配越多的规则优先级越高。
RULES: tuple[JitRule, ...] = (
    JitRule(
        name="analytics_sales",
        keywords=("orders", "totalprice", "subtotalprice", "createdat", "displayfinancialstatus", "ordersortkeys"),
        instruction=(
            "你现在处于「数据分析师」模式。处理这次返回时请：\n"
            "1) 计算关键聚合（环比、平均值、Top N）；\n"
            "2) 标注涨跌超 10% 的项目并给出可能原因（季节、促销、库存等）；\n"
            "3) 用简洁中文输出，关键数字直接给出，不要堆砌 JSON；\n"
            "4) 如果数据样本太小（< 10 条），明确说明结论的局限。"
        ),
    ),
    JitRule(
        name="inventory_ops",
        keywords=("inventoryitem", "inventorylevel", "inventoryquantity", "tracksinventory", "totalinventory"),
        instruction=(
            "你现在处于「运营顾问」模式。处理这次返回时请：\n"
            "1) 识别「低库存」商品（库存 < 7 天销量，结合最近订单速率）；\n"
            "2) 给出补货建议数量（保 14 天销量为目标）；\n"
            "3) 如果有 SKU 长时间无销售（> 30 天），提示考虑下架或促销清库存；\n"
            "4) 输出条目形式，每条 1-2 行，便于商家快速决策。"
        ),
    ),
    JitRule(
        name="content_creator",
        keywords=("descriptionhtml", "seo", "producttype", "vendor"),
        instruction=(
            "你现在处于「内容创作者」模式。生成内容请遵循：\n"
            "1) SEO 描述控制在 160 字符内；商品描述 200-400 字；\n"
            "2) 体现卖点（功能、材质、适用场景），避免空泛形容词；\n"
            "3) 参考同类商品的风格基调，保持品牌一致性；\n"
            "4) 写作完成后用 save_content 工具保存，并触发用户确认。"
        ),
    ),
    JitRule(
        name="customer_insights",
        keywords=("customer", "amountspent", "numberoforders", "lastorder"),
        instruction=(
            "你现在处于「CRM 顾问」模式。处理客户数据时请：\n"
            "1) 区分高价值客户（消费 Top 10%）与流失风险客户（30 天无订单）；\n"
            "2) 对每个分群给出 1 条可执行建议（折扣码、邮件、推荐商品）；\n"
            "3) 不要泄露客户原始 PII，描述时聚合或脱敏。"
        ),
    ),
    JitRule(
        name="promotion_design",
        keywords=("pricerule", "discountcode", "valuev2", "allocationmethod", "pricerulestatus"),
        instruction=(
            "你现在处于「促销设计」模式。处理促销数据请：\n"
            "1) 评估现有促销的使用率（usageCount）和有效期；\n"
            "2) 如果要新建促销，先给出预估影响（折扣力度 × 商品范围 × 持续时间）；\n"
            "3) 创建促销时必须用 create_promotion 工具，且明确告知用户："
            '"促销创建后会立即生效，请确认参数无误"。'
        ),
    ),
)


def detect_scenario(query: str) -> JitRule | None:
    """根据 GraphQL 查询字符串识别场景。返回匹配关键字最多的规则。

    匹配方式：子串（不带词边界），这样 camelCase 和单复数形式都能命中
    （例如 "priceRules" 会被 "pricerule" 关键字匹配）。
    """
    if not query:
        return None
    text = query.lower()
    best: tuple[JitRule, int] | None = None
    for rule in RULES:
        hits = sum(1 for kw in rule.keywords if kw in text)
        if hits == 0:
            continue
        if best is None or hits > best[1]:
            best = (rule, hits)
    return best[0] if best else None


def jit_instruction_for(query: str) -> str:
    """对外暴露：拿一条 GraphQL 查询，返回对应的 JIT 指令字符串（无匹配则返回通用指引）。"""
    rule = detect_scenario(query)
    if rule is not None:
        return f"[JIT:{rule.name}] {rule.instruction}"
    return (
        "[JIT:default] 按通用助手模式处理：先理解用户意图，再决定下一步行动。"
        "如果还需要更多数据，请继续调用 query_store_data。"
    )


# 写操作工具的固定 JIT（与查询无关，每次都附带）
WRITE_OP_JIT = (
    "[JIT:write_confirmation] 此操作不可撤销。在真正调用 Shopify 之前，"
    "你必须把 preview 结构以「操作确认卡」的形式呈现给商家，等待显式同意后再继续。"
    "如果商家拒绝，立即终止并说明已取消。"
)
