"""Sidekick CLI：命令行跟 Agent 对话。

用法：
    uv run python -m app.cli chat
    uv run python -m app.cli chat --task-type content_generation
    uv run python -m app.cli chat --model anthropic:claude-sonnet-4-5
    uv run python -m app.cli config show
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from sidekick_agent import AgentRunner, ConversationMessage, load_router_config

ROOT = Path(__file__).resolve().parents[3]
if (ROOT / ".env").exists():
    load_dotenv(ROOT / ".env")

app = typer.Typer(help="Sidekick POC CLI")
config_app = typer.Typer(help="查看/管理配置")
app.add_typer(config_app, name="config")
console = Console()


@app.command()
def chat(
    task_type: str = typer.Option(None, "--task-type", help="路由 task_type，默认由配置决定"),
    model: str | None = typer.Option(None, "--model", help="强制指定模型，覆盖路由"),
    system_prompt_preview: bool = typer.Option(False, "--show-system", help="启动前打印系统提示词前 300 字"),
) -> None:
    """进入交互式对话。Ctrl+D 或 输入 /quit 退出。"""
    runner = AgentRunner()
    if system_prompt_preview:
        console.print(Panel(runner.system_prompt[:300] + "...", title="System Prompt 前 300 字"))

    history: list[ConversationMessage] = []
    console.print(
        Panel.fit(
            "[bold green]Sidekick CLI[/] 已就绪。\n"
            "输入消息开始对话；[cyan]/quit[/] 退出，[cyan]/trace[/] 查看上一轮追踪，[cyan]/history[/] 看消息列表。",
            border_style="green",
        )
    )
    last_trace = None

    async def _one_turn(user: str) -> None:
        nonlocal last_trace
        result = await runner.run_turn(
            user,
            history=history,
            task_type=task_type,
            model_override=model,
        )
        last_trace = result.trace
        # 把这一轮的用户+助手消息保留到 history（不含 system）
        non_sys = [m for m in result.messages if m.role != "system"]
        history.clear()
        history.extend(non_sys)

        if result.trace.final_content:
            console.print(Panel(Markdown(result.trace.final_content), title="Sidekick", border_style="cyan"))
        if result.trace.tool_calls:
            t = Table(title="工具调用", show_lines=False)
            t.add_column("工具")
            t.add_column("OK")
            t.add_column("确认?")
            t.add_column("错误")
            for tc in result.trace.tool_calls:
                t.add_row(
                    tc["name"],
                    "✓" if tc["ok"] else "✗",
                    "是" if tc.get("requires_confirmation") else "",
                    (tc.get("error") or "")[:40],
                )
            console.print(t)
        if result.trace.error:
            console.print(f"[red]错误：{result.trace.error}[/red]")

    try:
        while True:
            try:
                user = console.input("[bold yellow]你 > [/] ")
            except (EOFError, KeyboardInterrupt):
                break
            user = user.strip()
            if not user:
                continue
            if user in {"/quit", "/exit"}:
                break
            if user == "/trace":
                if last_trace:
                    console.print_json(json.dumps(_trace_to_dict(last_trace), ensure_ascii=False, default=str))
                else:
                    console.print("[yellow]尚无 trace[/]")
                continue
            if user == "/history":
                for m in history:
                    console.print(f"[dim]{m.role}:[/] {(m.content or '')[:200]}")
                continue
            asyncio.run(_one_turn(user))
    finally:
        asyncio.run(runner.aclose())
    console.print("[dim]Bye.[/]")


def _trace_to_dict(trace) -> dict:
    from dataclasses import asdict

    return asdict(trace)


@config_app.command("show")
def config_show() -> None:
    """打印当前路由配置。"""
    cfg = load_router_config()
    t = Table(title=f"LLM Router Config (default={cfg.default_task_type})")
    t.add_column("task_type")
    t.add_column("primary")
    t.add_column("fallbacks")
    for name, entry in cfg.routes.items():
        t.add_row(name, entry.primary, ", ".join(entry.fallbacks))
    console.print(t)
    console.print(
        f"max_tokens={cfg.max_tokens} temperature={cfg.temperature} "
        f"agent_max_iterations={cfg.agent_max_iterations}"
    )


@app.command()
def version() -> None:
    console.print("sidekick-api 0.1.0 (M1 POC)")


if __name__ == "__main__":
    app()
