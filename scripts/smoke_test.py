"""M1 端到端 smoke test：用真实 Qwen + 真实 Shopify 跑一个问题，打印完整 trace。"""
from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

ROOT = Path(__file__).resolve().parent.parent
if (ROOT / ".env").exists():
    load_dotenv(ROOT / ".env")

from sidekick_agent import AgentRunner  # noqa: E402

console = Console()


async def main() -> int:
    question = sys.argv[1] if len(sys.argv) > 1 else "列出店里前 3 个商品的 title 和价格"
    console.print(Panel(f"[bold]问题:[/] {question}", border_style="yellow"))

    runner = AgentRunner()
    try:
        result = await runner.run_turn(question, task_type="analysis")
    finally:
        await runner.aclose()

    trace = result.trace
    console.print("\n[bold cyan]=== Final Content ===[/]")
    console.print(Panel(trace.final_content or "<空>", border_style="cyan"))

    console.print("\n[bold green]=== Trace ===[/]")
    trace_dict = asdict(trace)
    console.print_json(json.dumps(trace_dict, ensure_ascii=False, default=str))

    return 0 if trace.completed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
