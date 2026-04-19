"""跑一组 TestCase × 多模型，收集 trace + rubric 分数 + LLM Judge 分数。

保存：
- reports/raw/m1_<timestamp>/case_<id>_<model>.json：每条完整 trace
- reports/m1_<timestamp>_summary.json：聚合指标
- reports/m1_<timestamp>_report.md：人类可读报告
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from sidekick_agent import AgentRunner, JudgeScore, TurnTrace
from sidekick_tools import ShopifyClient

from .case_loader import TestCase, load_cases
from .judge import judge_one
from .rubric import RubricScore, aggregate, score

logger = logging.getLogger(__name__)

REPORTS_DIR = Path(__file__).resolve().parents[4] / "reports"


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


async def _run_one(
    case: TestCase,
    model: str,
    runner: AgentRunner,
) -> tuple[TurnTrace, str, list[dict]]:
    """跑一条测试用例，返回 trace / final_content / tool_calls_summary。"""
    result = await runner.run_turn(case.question, model_override=model, task_type=case.task_type)
    summary = [
        {
            "name": tc["name"],
            "ok": tc["ok"],
            "args_preview": (tc["arguments"][:200] + "...") if isinstance(tc["arguments"], str) and len(tc["arguments"]) > 200 else tc["arguments"],
        }
        for tc in result.trace.tool_calls
    ]
    return result.trace, result.trace.final_content or "", summary


SAMPLE_PRODUCT_ID_PLACEHOLDER = "{SAMPLE_PRODUCT_ID}"


async def _resolve_placeholders(cases: list[TestCase], shopify: ShopifyClient) -> None:
    """把 question 里的 {SAMPLE_PRODUCT_ID} 替换成 dev store 第一个真实商品 ID。

    避免 Agent 看到占位符正确地"理性拒绝执行"——这是数据问题不是 Agent 问题。
    """
    needs_id = any(SAMPLE_PRODUCT_ID_PLACEHOLDER in c.question for c in cases)
    if not needs_id:
        return
    try:
        resp = await shopify.graphql(
            '{ products(first: 1, sortKey: TITLE) { edges { node { id title } } } }'
        )
        edges = (resp.get("data") or {}).get("products", {}).get("edges") or []
        if not edges:
            logger.warning("dev store 无商品，无法解析 SAMPLE_PRODUCT_ID 占位符")
            return
        real_id = edges[0]["node"]["id"]
        title = edges[0]["node"]["title"]
        logger.info("解析 SAMPLE_PRODUCT_ID → %s (%s)", real_id, title)
        for c in cases:
            if SAMPLE_PRODUCT_ID_PLACEHOLDER in c.question:
                c.question = c.question.replace(SAMPLE_PRODUCT_ID_PLACEHOLDER, real_id.split("/")[-1])
    except Exception as e:  # noqa: BLE001
        logger.warning("占位符解析失败：%s", e)


async def run_evaluation(
    cases: list[TestCase],
    models: list[str],
    *,
    judge_model: str | None = None,
    output_dir: Path | None = None,
    with_judge: bool = True,
) -> dict[str, Any]:
    """对给定用例和模型跑完整评估。"""
    ts = _ts()
    out = output_dir or REPORTS_DIR / f"m1_{ts}"
    raw_dir = out / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    shopify = ShopifyClient()
    await _resolve_placeholders(cases, shopify)

    all_scores: list[RubricScore] = []
    judge_scores: dict[str, JudgeScore | None] = {}
    all_traces: list[dict[str, Any]] = []

    start = time.time()
    total_pairs = len(cases) * len(models)
    done = 0

    for case in cases:
        for model in models:
            done += 1
            logger.info("[%d/%d] Running %s × %s ...", done, total_pairs, case.id, model)
            runner = AgentRunner(shopify_client=shopify)
            try:
                try:
                    trace, final_content, tool_summary = await _run_one(case, model, runner)
                except Exception as e:  # noqa: BLE001
                    logger.exception("case %s × %s 异常", case.id, model)
                    # 构造一个标记失败的 trace
                    trace = TurnTrace(task_type=case.task_type, error=str(e))
                    final_content = ""
                    tool_summary = []
            finally:
                # 复用 shopify client，不关
                runner._shopify = None  # type: ignore[attr-defined]

            # rubric 评分
            rs = score(case, trace, model)
            all_scores.append(rs)

            # LLM-as-Judge
            judge: JudgeScore | None = None
            if with_judge and final_content:
                try:
                    judge = await judge_one(
                        case,
                        final_content,
                        tool_summary,
                        judge_model=judge_model or "dashscope/qwen-max",
                    )
                except Exception as e:  # noqa: BLE001
                    logger.warning("judge 失败: %s", e)
            judge_scores[f"{case.id}|{model}"] = judge

            record = {
                "case_id": case.id,
                "category": case.category,
                "question": case.question,
                "model": model,
                "rubric": rs.as_dict(),
                "judge": judge.model_dump() if judge else None,
                "trace": asdict(trace),
                "final_content": final_content,
                "tool_calls_summary": tool_summary,
            }
            all_traces.append(record)
            safe_id = case.id.replace("/", "_")
            safe_model = model.replace(":", "_").replace("/", "_")
            (raw_dir / f"{safe_id}__{safe_model}.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )

    await shopify.aclose()

    rubric_summary = aggregate(all_scores)
    judge_summary = _aggregate_judge(judge_scores)
    elapsed = time.time() - start

    summary = {
        "timestamp": ts,
        "elapsed_s": elapsed,
        "cases_count": len(cases),
        "models": models,
        "judge_model": judge_model,
        "rubric_summary": rubric_summary,
        "judge_summary": judge_summary,
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    # Markdown 报告
    md = _render_markdown(summary, all_scores, judge_scores, cases)
    (out / "report.md").write_text(md, encoding="utf-8")

    logger.info("评估完成：%.1fs，报告写到 %s", elapsed, out)
    return {"summary": summary, "output_dir": str(out)}


def _aggregate_judge(judge_scores: dict[str, JudgeScore | None]) -> dict[str, Any]:
    from collections import defaultdict

    by_model: dict[str, list[JudgeScore]] = defaultdict(list)
    for key, js in judge_scores.items():
        if js is None:
            continue
        model = key.split("|", 1)[1]
        by_model[model].append(js)

    out: dict[str, Any] = {}
    for model, ss in by_model.items():
        n = len(ss)
        if n == 0:
            continue
        out[model] = {
            "n": n,
            "avg_overall": sum(s.overall for s in ss) / n,
            "tool_selection_correct_rate": sum(1 for s in ss if s.tool_selection_correct) / n,
            "jit_instruction_followed_rate": sum(1 for s in ss if s.jit_instruction_followed) / n,
            "graphql_syntax_valid_rate": sum(1 for s in ss if s.graphql_syntax_valid) / max(1, sum(1 for s in ss if s.graphql_syntax_valid is not None)),
        }
    return out


def _render_markdown(
    summary: dict[str, Any],
    scores: list[RubricScore],
    judge_scores: dict[str, JudgeScore | None],
    cases: list[TestCase],
) -> str:
    lines: list[str] = []
    lines.append(f"# M1 可行性评估报告 · {summary['timestamp']}")
    lines.append("")
    lines.append(f"**耗时**：{summary['elapsed_s']:.1f}s · **用例数**：{summary['cases_count']} × **模型数**：{len(summary['models'])}")
    lines.append("")
    lines.append("## 关键指标对比")
    lines.append("")
    lines.append("| 模型 | hard_pass | 工具选对 | JIT 命中 | GraphQL 语法 | 确认流程 | 完成率 | avg 延迟 | avg tokens |")
    lines.append("|------|-----------|---------|---------|-------------|---------|--------|---------|-----------|")
    for model, s in summary["rubric_summary"].items():
        lines.append(
            f"| {model} | {s['hard_pass_rate']:.0%} | {s['tool_selection_accuracy']:.0%} | "
            f"{s['jit_category_hit']:.0%} | {s['graphql_syntax_ok']:.0%} | {s['confirmation_respected']:.0%} | "
            f"{s['completed']:.0%} | {s['avg_latency_s']:.1f}s | {s['avg_total_tokens']:.0f} |"
        )
    lines.append("")

    if summary.get("judge_summary"):
        lines.append("## LLM-as-Judge（1-5 分）")
        lines.append("")
        lines.append("| 模型 | 样本数 | 综合均分 | 工具选对率 | JIT 遵循率 |")
        lines.append("|------|--------|---------|-----------|----------|")
        for model, s in summary["judge_summary"].items():
            lines.append(
                f"| {model} | {s['n']} | {s['avg_overall']:.2f} | "
                f"{s['tool_selection_correct_rate']:.0%} | {s['jit_instruction_followed_rate']:.0%} |"
            )
        lines.append("")

    # 决策门检查
    lines.append("## M1 Go/No-Go 决策门")
    lines.append("")
    lines.append("方案 A 的 M1 通过标准（任一模型达到）：")
    lines.append("- JIT 指令遵循率 ≥ 80%（rubric 的 jit_category_hit 或 judge 的 jit_instruction_followed_rate）")
    lines.append("- 工具选择准确率 ≥ 85%")
    lines.append("- GraphQL 语法正确率 ≥ 90%")
    lines.append("")
    for model, s in summary["rubric_summary"].items():
        pass_flags = []
        if s["jit_category_hit"] >= 0.80:
            pass_flags.append("JIT ✅")
        else:
            pass_flags.append(f"JIT ⚠️ ({s['jit_category_hit']:.0%})")
        if s["tool_selection_accuracy"] >= 0.85:
            pass_flags.append("工具 ✅")
        else:
            pass_flags.append(f"工具 ⚠️ ({s['tool_selection_accuracy']:.0%})")
        if s["graphql_syntax_ok"] >= 0.90:
            pass_flags.append("GraphQL ✅")
        else:
            pass_flags.append(f"GraphQL ⚠️ ({s['graphql_syntax_ok']:.0%})")
        lines.append(f"- **{model}**: {' · '.join(pass_flags)}")
    lines.append("")

    # 按类别分组
    lines.append("## 按类别细分")
    lines.append("")
    from collections import defaultdict

    cat_scores: dict[str, list[RubricScore]] = defaultdict(list)
    for s in scores:
        cat_scores[s.category].append(s)
    for cat, ss in sorted(cat_scores.items()):
        n = len(ss)
        if n == 0:
            continue
        hard = sum(1 for s in ss if s.hard_pass) / n
        lines.append(f"- **{cat}**（{n}次）：hard_pass={hard:.0%}")
    lines.append("")

    # 逐条详情
    lines.append("## 逐条结果")
    lines.append("")
    case_by_id = {c.id: c for c in cases}
    for s in scores:
        c = case_by_id.get(s.case_id)
        if c is None:
            continue
        judge = judge_scores.get(f"{s.case_id}|{s.model}")
        judge_line = f" · judge={judge.overall}/5" if judge else ""
        status = "✅" if s.hard_pass else "❌"
        lines.append(f"### {status} [{s.model}] {s.case_id} · {c.category}{judge_line}")
        lines.append(f"> {c.question}")
        lines.append("")
        checks = [
            ("工具选对", s.tool_selection_accuracy),
            ("调用数达标", s.min_tool_calls_met),
            ("JIT 命中", s.jit_category_hit),
            ("GraphQL 语法", s.graphql_syntax_ok),
            ("确认流程", s.requires_confirmation_respected),
            ("完成", s.completed),
        ]
        lines.append(" · ".join(f"{'✓' if ok else '✗'} {name}" for name, ok in checks))
        lines.append(f"调用次数 {s.tool_calls_count} · 延迟 {s.latency_s:.1f}s · tokens {s.total_tokens}")
        if s.notes:
            for n in s.notes:
                lines.append(f"- ⚠️ {n}")
        if judge and judge.reasoning:
            lines.append(f"- 📝 Judge: {judge.reasoning}")
        lines.append("")

    return "\n".join(lines)


# CLI 入口
def main() -> None:
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="跑 M1 评估")
    parser.add_argument(
        "--models",
        default="dashscope:qwen-max",
        help="逗号分隔的模型列表，例如 dashscope:qwen-max,dashscope:qwen-plus",
    )
    parser.add_argument(
        "--categories",
        default="",
        help="只跑指定类别（逗号分隔），空=全部",
    )
    parser.add_argument(
        "--case-ids",
        default="",
        help="只跑指定 case id（逗号分隔），空=全部",
    )
    parser.add_argument("--no-judge", action="store_true", help="跳过 LLM-as-Judge")
    parser.add_argument(
        "--judge-model",
        default="dashscope/qwen-max",
        help="Judge 模型（LiteLLM 格式，例如 dashscope/qwen-max）",
    )
    args = parser.parse_args()

    cases = load_cases()
    if args.categories:
        wanted = {c.strip() for c in args.categories.split(",") if c.strip()}
        cases = [c for c in cases if c.category in wanted]
    if args.case_ids:
        wanted_ids = {c.strip() for c in args.case_ids.split(",") if c.strip()}
        cases = [c for c in cases if c.id in wanted_ids]
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    print(f"即将评估 {len(cases)} 条用例 × {len(models)} 模型 = {len(cases) * len(models)} 次运行")

    result = asyncio.run(
        run_evaluation(
            cases,
            models,
            judge_model=args.judge_model,
            with_judge=not args.no_judge,
        )
    )
    print(f"完成。报告：{result['output_dir']}/report.md")


if __name__ == "__main__":
    main()
