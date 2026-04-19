"""租户上下文：从 YAML 加载注册表，按 shop_domain 解析 token + 配置。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from .config import ROOT


@dataclass(frozen=True)
class TenantContext:
    shop_domain: str
    display_name: str
    admin_token: str
    api_version: str
    locale: str
    default_task_type: str


class TenantNotFoundError(KeyError):
    pass


class TenantTokenMissingError(RuntimeError):
    """配置里指向了某 env var，但环境里没设。"""


@lru_cache(maxsize=1)
def _load_registry() -> dict[str, dict]:
    env = os.environ.get("SIDEKICK_TENANTS_CONFIG", "").strip()
    path = Path(env) if env else (ROOT / "config" / "tenants.yaml")
    if not path.exists():
        raise FileNotFoundError(f"租户配置不存在：{path}")
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    out: dict[str, dict] = {}
    for t in raw.get("tenants", []) or []:
        out[t["shop_domain"]] = t
    return out


def list_tenants() -> list[dict]:
    """对外返回 UI 切换器需要的最小字段（不含 token）。"""
    return [
        {
            "shop_domain": t["shop_domain"],
            "display_name": t.get("display_name", t["shop_domain"]),
            "locale": t.get("locale", "zh-CN"),
        }
        for t in _load_registry().values()
    ]


def resolve_tenant(shop_domain: str) -> TenantContext:
    registry = _load_registry()
    if shop_domain not in registry:
        raise TenantNotFoundError(f"未注册的 shop_domain: {shop_domain}")
    cfg = registry[shop_domain]
    token_env = cfg.get("token_env", "SHOPIFY_ADMIN_TOKEN")
    token = os.environ.get(token_env, "").strip()
    if not token:
        raise TenantTokenMissingError(
            f"租户 {shop_domain} 的 token 通过 {token_env} 注入，但环境变量为空"
        )
    return TenantContext(
        shop_domain=shop_domain,
        display_name=cfg.get("display_name", shop_domain),
        admin_token=token,
        api_version=cfg.get("api_version", "2025-10"),
        locale=cfg.get("locale", "zh-CN"),
        default_task_type=cfg.get("default_task_type", "analysis"),
    )


def reload_registry() -> None:
    _load_registry.cache_clear()
