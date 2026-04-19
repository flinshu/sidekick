"""加载 curated 的 Shopify schema subset，同时提供 token 计数校验。"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

# __file__ = .../packages/tools/src/sidekick_tools/schema_loader.py
# parents[0] = sidekick_tools, [1] = src, [2] = tools, [3] = packages, [4] = repo root
# schema file sits at packages/tools/shopify_schema_subset.graphql → parents[2]
SCHEMA_FILE = Path(__file__).resolve().parents[2] / "shopify_schema_subset.graphql"
MAX_TOKENS_DEFAULT = 15_000


@lru_cache(maxsize=1)
def load_schema_subset() -> str:
    if not SCHEMA_FILE.exists():
        raise FileNotFoundError(f"Schema subset 文件不存在：{SCHEMA_FILE}")
    return SCHEMA_FILE.read_text(encoding="utf-8")


def count_tokens(text: str, model: str = "gpt-4o") -> int:
    """用 tiktoken 粗略估算 token 数；作为不同模型的 baseline。"""
    try:
        import tiktoken  # type: ignore[import-not-found]

        try:
            enc = tiktoken.encoding_for_model(model)
        except KeyError:
            enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except ImportError:
        # 退化到字符数 / 4 粗估
        return len(text) // 4


def assert_subset_within_budget(max_tokens: int = MAX_TOKENS_DEFAULT) -> int:
    schema = load_schema_subset()
    tokens = count_tokens(schema)
    if tokens > max_tokens:
        raise AssertionError(
            f"Schema subset 太大：{tokens} tokens 超过上限 {max_tokens}。请裁剪字段或类型。"
        )
    return tokens


if __name__ == "__main__":
    tokens = assert_subset_within_budget()
    print(f"Schema subset OK, 约 {tokens} tokens（上限 {MAX_TOKENS_DEFAULT}）")
