"""集成测试：跑评估并检查阈值（M3 9.4 + 9.6）。

跳过条件：
- 没设 DASHSCOPE_API_KEY 等真实 LLM key（CI 跳过；只在 dev / dispatch 跑）
- 没设 SHOPIFY_ADMIN_TOKEN（同上）

跑法：
    uv run pytest tests/integration/test_evaluation_thresholds.py -v -s --models=dashscope:qwen-plus

自定义 --models 选项让 CI 可以传不同模型集合。
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from sidekick_evals import load_cases, run_evaluation

# 来自 M1 的 baseline；任何核心指标低于 baseline 超过 10% 视为回归（M3 Task 9.6）
M1_BASELINE = {
    "hard_pass_rate": 0.85,  # M2.5 修后实际 0.85（qwen-plus）/ 1.00（glm-5）
    "tool_selection_accuracy": 0.90,
    "graphql_syntax_ok": 0.95,
    "jit_category_hit": 0.90,
}
REGRESSION_TOLERANCE = 0.10  # 10%


def _has_api_keys() -> bool:
    """有任意一家可用就跑。"""
    return any(
        os.environ.get(k)
        for k in ("DASHSCOPE_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ZHIPU_API_KEY")
    )


def _has_shopify() -> bool:
    return bool(os.environ.get("SHOPIFY_ADMIN_TOKEN"))


pytestmark = pytest.mark.skipif(
    not (_has_api_keys() and _has_shopify()),
    reason="需要真实 LLM API key + Shopify token；本地手动运行或 GitHub Actions workflow_dispatch",
)


@pytest.fixture(scope="module")
def models_under_test() -> list[str]:
    raw = os.environ.get("SIDEKICK_TEST_MODELS", "dashscope:qwen-plus")
    return [m.strip() for m in raw.split(",") if m.strip()]


@pytest.fixture(scope="module")
def categories_under_test() -> list[str]:
    raw = os.environ.get("SIDEKICK_TEST_CATEGORIES", "sales_analytics")
    return [c.strip() for c in raw.split(",") if c.strip()]


@pytest.mark.asyncio
async def test_meets_baseline(models_under_test: list[str], categories_under_test: list[str]) -> None:
    """跑一组 case × model，断言任一模型在每个核心指标上不低于 baseline - 10%。"""
    cases = [c for c in load_cases() if c.category in categories_under_test]
    assert cases, f"没有匹配类别的用例：{categories_under_test}"

    result = await run_evaluation(
        cases,
        models_under_test,
        with_judge=False,  # CI 不开 Judge 节省时间和钱
    )
    rubric_summary = result["summary"]["rubric_summary"]

    failures: list[str] = []
    for model, stats in rubric_summary.items():
        for metric, baseline in M1_BASELINE.items():
            actual = stats.get(metric)
            if actual is None:
                continue
            min_acceptable = baseline - REGRESSION_TOLERANCE
            if actual < min_acceptable:
                failures.append(
                    f"  - [{model}] {metric}: 实测 {actual:.2%} < 可接受下限 {min_acceptable:.2%}"
                    f"（baseline {baseline:.2%}）"
                )

    if failures:
        msg = "评估指标回归（任一模型不达 baseline-10%）：\n" + "\n".join(failures)
        pytest.fail(msg)


@pytest.mark.asyncio
async def test_no_hard_failures_in_smoke(models_under_test: list[str]) -> None:
    """sales-001 是最简单的查询；任何模型都应该通过。"""
    cases = [c for c in load_cases() if c.id == "sales-001"]
    if not cases:
        pytest.skip("sales-001 用例不存在")
    result = await run_evaluation(cases, models_under_test, with_judge=False)
    rubric = result["summary"]["rubric_summary"]
    for model, stats in rubric.items():
        assert stats["hard_pass_rate"] == 1.0, (
            f"{model} 在 sales-001 烟雾测试上未通过 hard_pass"
        )
