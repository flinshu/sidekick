"""跑一批模拟对话 + 输出汇总报告（M3 Task 10.5）。

CLI:
    uv run python -m sidekick_evals.sim_runner \
        --personas newbie,power,adversarial \
        --target-model dashscope:qwen-plus \
        --driver-model zhipu:glm-5 \
        --runs-per-persona 3 \
        --max-turns 5
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from sidekick_agent import AgentRunner
from sidekick_tools import ShopifyClient

from .personas import PERSONAS, get_persona
from .simulator import SimulationResult, simulate_one

logger = logging.getLogger(__name__)
REPORTS_DIR = Path(__file__).resolve().parents[4] / "reports"


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


async def run_batch(
    personas: list[str],
    target_model: str,
    driver_model: str,
    runs_per_persona: int,
    max_turns: int,
) -> dict:
    ts = _ts()
    out_dir = REPORTS_DIR / f"sim_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    shopify = ShopifyClient()
    runner = AgentRunner(shopify_client=shopify)

    results: list[SimulationResult] = []
    try:
        for pid in personas:
            persona = get_persona(pid)
            for run_idx in range(runs_per_persona):
                seed = persona.seed_prompts[run_idx % len(persona.seed_prompts)]
                logger.info("[%s #%d] seed=%s", pid, run_idx, seed[:30])
                r = await simulate_one(
                    persona,
                    seed,
                    runner=runner,
                    driver_model=driver_model,
                    max_turns=max_turns,
                )
                # 强制覆盖被测模型为 target_model 是不正确的——run_turn 使用配置中的默认。
                # 真要锁定模型，可在 simulate_one 里传 model_override。
                results.append(r)
                # 单条落盘
                fp = out_dir / f"{pid}_{run_idx}.json"
                fp.write_text(
                    json.dumps(asdict(r), ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8",
                )
    finally:
        await shopify.aclose()

    summary = _summarize(results, target_model, driver_model)
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    (out_dir / "report.md").write_text(_render_md(summary, results), encoding="utf-8")
    return {"summary": summary, "output_dir": str(out_dir)}


def _summarize(results: list[SimulationResult], target: str, driver: str) -> dict:
    by_persona: dict[str, list[SimulationResult]] = {}
    for r in results:
        by_persona.setdefault(r.persona_id, []).append(r)

    out = {
        "target_model": target,
        "driver_model": driver,
        "total_runs": len(results),
        "per_persona": {},
    }
    for pid, items in by_persona.items():
        n = len(items)
        avg_turns = sum(r.total_turns for r in items) / n if n else 0
        avg_tools = sum(r.total_tool_calls for r in items) / n if n else 0
        finished = sum(1 for r in items if r.finished_reason in {"user_satisfied", "max_turns"})
        errors = sum(r.error_count for r in items)
        adversarial_refused = (
            sum(1 for r in items if r.refused_unsafe) if pid == "adversarial" else None
        )
        out["per_persona"][pid] = {
            "runs": n,
            "avg_turns": avg_turns,
            "avg_tool_calls": avg_tools,
            "finished_normally": finished,
            "agent_errors": errors,
            "adversarial_refused": adversarial_refused,
        }
    return out


def _render_md(summary: dict, results: list[SimulationResult]) -> str:
    lines: list[str] = ["# 用户模拟回归报告", ""]
    lines.append(f"- target Agent 模型：`{summary['target_model']}`")
    lines.append(f"- driver 模拟商家模型：`{summary['driver_model']}`")
    lines.append(f"- 总场景数：{summary['total_runs']}")
    lines.append("")
    lines.append("## 按画像聚合")
    lines.append("")
    lines.append("| 画像 | 场景数 | 平均轮次 | 平均工具调用 | Agent 错误 | 越权拒绝率 |")
    lines.append("|------|:----:|:------:|:----------:|:--------:|:--------:|")
    for pid, s in summary["per_persona"].items():
        adv = (
            f"{s['adversarial_refused']}/{s['runs']}" if s["adversarial_refused"] is not None else "—"
        )
        lines.append(
            f"| {pid} | {s['runs']} | {s['avg_turns']:.1f} | {s['avg_tool_calls']:.1f} | "
            f"{s['agent_errors']} | {adv} |"
        )
    lines.append("")
    lines.append("## 逐条详情")
    lines.append("")
    for r in results:
        lines.append(f"### [{r.persona_id}] seed: {r.seed_prompt}")
        lines.append(f"- 结束原因：`{r.finished_reason}`，轮次：{r.total_turns}，工具调用：{r.total_tool_calls}")
        for i, t in enumerate(r.turns):
            text = (t.agent_final or "(无)").replace("\n", " ")[:200]
            lines.append(f"  - 轮 {i + 1} 用户：{t.user_message[:80]}")
            lines.append(f"  - 轮 {i + 1} Agent：{text}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--personas", default="newbie,power,adversarial")
    p.add_argument("--target-model", default="dashscope:qwen-plus", help="被测 Sidekick 模型（仅用于报告标记，实际由 router 决定）")
    p.add_argument("--driver-model", default="zhipu:glm-5", help="模拟商家用的模型，必须不同家")
    p.add_argument("--runs-per-persona", type=int, default=2)
    p.add_argument("--max-turns", type=int, default=5)
    args = p.parse_args()

    personas = [s.strip() for s in args.personas.split(",") if s.strip()]
    print(f"模拟：{personas} × {args.runs_per_persona} runs × ≤{args.max_turns} turns")
    out = asyncio.run(
        run_batch(
            personas, args.target_model, args.driver_model, args.runs_per_persona, args.max_turns
        )
    )
    print(f"完成。报告：{out['output_dir']}/report.md")


if __name__ == "__main__":
    main()
