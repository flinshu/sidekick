"""测试当前配置的模型 API key 是否能正常调用（不接 Shopify，纯 LLM 连通性）。

用法：
    uv run python scripts/llm_ping.py
    uv run python scripts/llm_ping.py --model dashscope:qwen-max
    uv run python scripts/llm_ping.py --task analysis
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console

ROOT = Path(__file__).resolve().parent.parent
if (ROOT / ".env").exists():
    load_dotenv(ROOT / ".env")

import litellm  # noqa: E402

from sidekick_agent import load_router_config  # noqa: E402
from sidekick_agent.runner import _extra_kwargs_for, _to_litellm_model  # noqa: E402

console = Console()

litellm.telemetry = False
litellm.drop_params = True


async def try_model(model: str) -> tuple[bool, str]:
    litellm_model = _to_litellm_model(model)
    extra = _extra_kwargs_for(model)
    try:
        resp = await litellm.acompletion(
            model=litellm_model,
            messages=[
                {"role": "system", "content": "你是一个测试助手。"},
                {"role": "user", "content": "回复一个字：ok"},
            ],
            max_tokens=20,
            temperature=0,
            **extra,
        )
        content = resp["choices"][0]["message"].get("content") or ""
        return True, content.strip()
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def main(
    model: str = typer.Option(None, "--model", help="指定模型，如 dashscope:qwen-max"),
    task: str = typer.Option(None, "--task", help="按 task_type 解析（primary 模型）"),
) -> None:
    cfg = load_router_config()
    if model:
        models = [model]
    elif task:
        models = [cfg.resolve(task).primary]
    else:
        models = [entry.primary for entry in cfg.routes.values()]
        # 去重
        seen = []
        for m in models:
            if m not in seen:
                seen.append(m)
        models = seen

    has_key = {
        "dashscope": bool(os.environ.get("DASHSCOPE_API_KEY")),
        "anthropic": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "openai": bool(os.environ.get("OPENAI_API_KEY")),
        "zhipu": bool(os.environ.get("ZHIPU_API_KEY")),
    }
    console.print(f"[dim]API key 配置状态: {has_key}[/]")

    async def run() -> int:
        any_fail = False
        for m in models:
            provider = m.split(":", 1)[0]
            if not has_key.get(provider, False):
                console.print(f"⚠️  [yellow]{m}[/] — 未配置 {provider.upper()}_API_KEY，跳过")
                continue
            ok, msg = await try_model(m)
            if ok:
                console.print(f"✅ [green]{m}[/] → {msg[:80]}")
            else:
                any_fail = True
                console.print(f"❌ [red]{m}[/] → {msg[:200]}")
        return 1 if any_fail else 0

    sys.exit(asyncio.run(run()))


if __name__ == "__main__":
    typer.run(main)
