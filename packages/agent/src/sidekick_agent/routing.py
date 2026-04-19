"""基于 YAML 配置的 LLM 路由器。

设计：
- 路由按 task_type 解析：primary + fallbacks 列表
- 不绑定任何 provider：调用方只拿到"下一个该试的 model id"
- 具体 LLM 调用在 runner.py 里通过 LiteLLM 执行，这里只做"要用哪个"的决策
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml


@dataclass(frozen=True)
class RouteEntry:
    task_type: str
    primary: str
    fallbacks: tuple[str, ...]

    def all_models(self) -> tuple[str, ...]:
        return (self.primary, *self.fallbacks)


@dataclass(frozen=True)
class RouterConfig:
    default_task_type: str
    routes: dict[str, RouteEntry]
    max_tokens: int
    temperature: float
    agent_max_iterations: int
    agent_max_retries_per_call: int

    def resolve(self, task_type: str | None) -> RouteEntry:
        key = task_type or self.default_task_type
        if key in self.routes:
            return self.routes[key]
        return self.routes[self.default_task_type]


def _default_config_path() -> Path:
    env = os.environ.get("SIDEKICK_ROUTER_CONFIG", "").strip()
    if env:
        return Path(env)
    # .../packages/agent/src/sidekick_agent/routing.py → parents[4] 是 repo root
    return Path(__file__).resolve().parents[4] / "config" / "llm_router.yaml"


DEFAULT_CONFIG_PATH = _default_config_path()


@lru_cache(maxsize=4)
def load_router_config(path: Path | None = None) -> RouterConfig:
    config_path = path or DEFAULT_CONFIG_PATH
    if not config_path.exists():
        raise FileNotFoundError(f"找不到路由配置：{config_path}")
    with config_path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    routes_raw = raw.get("routes") or {}
    routes: dict[str, RouteEntry] = {}
    for name, cfg in routes_raw.items():
        routes[name] = RouteEntry(
            task_type=name,
            primary=cfg["primary"],
            fallbacks=tuple(cfg.get("fallbacks") or ()),
        )

    gen = raw.get("generation") or {}
    agent = raw.get("agent") or {}
    return RouterConfig(
        default_task_type=raw.get("default_task_type") or "analysis",
        routes=routes,
        max_tokens=int(gen.get("max_tokens", 4096)),
        temperature=float(gen.get("temperature", 0.3)),
        agent_max_iterations=int(agent.get("max_iterations", 10)),
        agent_max_retries_per_call=int(agent.get("max_retries_per_call", 3)),
    )


def reload_router_config() -> None:
    """清理 cache，强制下次读盘。"""
    load_router_config.cache_clear()
