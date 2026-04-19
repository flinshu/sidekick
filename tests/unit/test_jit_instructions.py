from sidekick_tools import detect_scenario, jit_instruction_for


def test_sales_query_detects_analytics_scenario() -> None:
    query = "{ orders(first: 10) { edges { node { totalPrice createdAt } } } }"
    rule = detect_scenario(query)
    assert rule is not None
    assert rule.name == "analytics_sales"


def test_inventory_query_detects_inventory_scenario() -> None:
    query = """
    { inventoryItem(id: "gid://shopify/InventoryItem/1") {
        inventoryLevels(first: 3) { edges { node { quantities(names: ["available"]) { quantity } } } }
      } }
    """
    rule = detect_scenario(query)
    assert rule is not None
    assert rule.name == "inventory_ops"


def test_product_content_detects_content_creator() -> None:
    query = "{ product(id: \"x\") { title descriptionHtml seo { title description } productType vendor } }"
    rule = detect_scenario(query)
    assert rule is not None
    assert rule.name == "content_creator"


def test_customer_query_detects_customer_insights() -> None:
    query = "{ customers(first: 5) { edges { node { email amountSpent { amount } numberOfOrders } } } }"
    rule = detect_scenario(query)
    assert rule is not None
    assert rule.name == "customer_insights"


def test_price_rule_query_detects_promotion_design() -> None:
    query = "{ priceRules(first: 5) { edges { node { title status usageCount valueV2 { __typename } allocationMethod } } } }"
    rule = detect_scenario(query)
    assert rule is not None
    assert rule.name == "promotion_design"


def test_empty_query_returns_none() -> None:
    assert detect_scenario("") is None


def test_instruction_wrapper_includes_scenario_tag() -> None:
    instr = jit_instruction_for("{ orders { edges { node { totalPrice } } } }")
    assert instr.startswith("[JIT:analytics_sales]")


def test_instruction_wrapper_default_fallback() -> None:
    instr = jit_instruction_for("{ foo }")
    assert "[JIT:default]" in instr
