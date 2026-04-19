"""语义缓存指标。"""
from __future__ import annotations

from .api_models import CacheMetrics
from .semantic_cache import get_cache


async def get_metrics(tenant_id: str | None = None) -> CacheMetrics:  # noqa: D401

    cache = get_cache()
    s = cache.stats(tenant_id)
    return CacheMetrics(
        total_queries=s["total"],
        hits=s["hits"],
        misses=s["misses"],
        # M2 占坑：1h/24h 滚动窗口待 M3 上 Prometheus 实现
        hit_rate_1h=s["hit_rate"],
        hit_rate_24h=s["hit_rate"],
    )
