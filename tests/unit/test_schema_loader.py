from sidekick_tools import assert_subset_within_budget, count_tokens, load_schema_subset


def test_schema_subset_loads() -> None:
    text = load_schema_subset()
    assert "type Product" in text
    assert "type Order" in text
    assert "type InventoryItem" in text
    assert "type PriceRule" in text


def test_schema_subset_within_budget() -> None:
    tokens = assert_subset_within_budget()
    assert 500 < tokens < 15_000


def test_count_tokens_approximation() -> None:
    # 对很短的字符串，token 数应该大于 0
    assert count_tokens("hello world") > 0
