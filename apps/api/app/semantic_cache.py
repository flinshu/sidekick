"""语义缓存（M3 升级版：Qdrant 向量索引 + sentence-transformers 真嵌入）。

设计：
- 每个 query 在写入时计算 384-d embedding
- 存储：Qdrant collection `sidekick_cache`，payload 含 tenant_id / query / response / metadata / expires_at
- 命中：按 tenant_id + cosine sim ≥ 阈值 + 未过期检索
- 失效：按 keyword 子串匹配淘汰（M3 这一步保持 keyword 实现，未来可扩到 embedding）

兼容性：sentence-transformers 加载失败时 fallback 到 sha256 完全匹配（M2 简化版）。
这样在没装大依赖的开发机也能跑。
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import redis.asyncio as aioredis

from .config import get_settings

logger = logging.getLogger(__name__)

DEFAULT_TTL_ANALYSIS = timedelta(hours=24)
DEFAULT_TTL_DYNAMIC = timedelta(hours=1)
SIMILARITY_THRESHOLD = float(__import__("os").environ.get("SIDEKICK_CACHE_THRESHOLD", "0.85"))
# 0.85 实测：同时段 paraphrase（如"上周销量" vs "上一周销售情况"）能命中（~0.85+），
# 不同时段（如"上周销量" vs "本周销量"）不会误命中（~0.78）。
# 调高（0.92）对中文 MiniLM 太严，连同义改写都不命中；调低（0.78）会误命中近邻意图。
# Task 11.2 在全量回归后会用真实数据 sweep 验证。
QDRANT_COLLECTION = "sidekick_cache"
EMBEDDING_DIM = 384


class SemanticCache:
    """M3 语义缓存。Qdrant + sentence-transformer。失败 fallback 到 sha256 完全匹配。"""

    def __init__(
        self,
        redis_url: str | None = None,
        qdrant_url: str | None = None,
        namespace: str = "sidekick:cache",
    ) -> None:
        settings = get_settings()
        self._redis_url = redis_url or settings.redis_url
        self._qdrant_url = qdrant_url or settings.qdrant_url
        self._namespace = namespace
        self._redis: aioredis.Redis | None = None
        self._qdrant = None
        self._embedder = None
        self._mode = "embedding"  # 或 "sha256"（fallback）
        self._stats: dict[str, dict[str, int]] = defaultdict(
            lambda: {"hits": 0, "misses": 0}
        )

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._redis

    def _get_qdrant_and_embedder(self):
        """惰性加载 Qdrant client 和 embedder。失败回 (None, None)，触发 sha256 fallback。"""
        if self._mode == "sha256":
            return None, None
        if self._qdrant is not None and self._embedder is not None:
            return self._qdrant, self._embedder
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.http import models as qm

            from .embeddings import get_embedder

            client = QdrantClient(url=self._qdrant_url)
            # 确保 collection 存在
            existing = {c.name for c in client.get_collections().collections}
            if QDRANT_COLLECTION not in existing:
                client.create_collection(
                    collection_name=QDRANT_COLLECTION,
                    vectors_config=qm.VectorParams(size=EMBEDDING_DIM, distance=qm.Distance.COSINE),
                )
                logger.info("Qdrant: 创建 collection %s", QDRANT_COLLECTION)
            self._qdrant = client
            self._embedder = get_embedder()
            return self._qdrant, self._embedder
        except Exception as e:  # noqa: BLE001
            logger.warning("Qdrant/Embedder 初始化失败 → fallback sha256：%s", e)
            self._mode = "sha256"
            return None, None

    async def aclose(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    # ===== 主 API =====

    async def get(self, tenant_id: str, query: str) -> dict[str, Any] | None:
        qdrant, embedder = self._get_qdrant_and_embedder()
        if qdrant is None:
            return await self._get_sha256(tenant_id, query)
        # embedding 路径
        try:
            vec = embedder.encode(query)
            from qdrant_client.http import models as qm

            response = qdrant.query_points(
                collection_name=QDRANT_COLLECTION,
                query=vec.tolist(),
                query_filter=qm.Filter(
                    must=[qm.FieldCondition(key="tenant_id", match=qm.MatchValue(value=tenant_id))]
                ),
                limit=1,
                score_threshold=SIMILARITY_THRESHOLD,
                with_payload=True,
            )
            results = response.points
            if not results:
                self._stats[tenant_id]["misses"] += 1
                return None
            best = results[0]
            payload = best.payload or {}
            # 过期检查
            exp_iso = payload.get("expires_at_iso")
            if exp_iso and datetime.fromisoformat(exp_iso) < datetime.utcnow():
                qdrant.delete(
                    collection_name=QDRANT_COLLECTION,
                    points_selector=qm.PointIdsList(points=[best.id]),
                )
                self._stats[tenant_id]["misses"] += 1
                return None
            self._stats[tenant_id]["hits"] += 1
            payload["_similarity"] = best.score
            return payload
        except Exception as e:  # noqa: BLE001
            logger.warning("语义缓存查询失败：%s", e)
            self._stats[tenant_id]["misses"] += 1
            return None

    async def set(
        self,
        tenant_id: str,
        query: str,
        response: str,
        *,
        is_dynamic: bool = False,
        metadata: dict | None = None,
    ) -> None:
        ttl = DEFAULT_TTL_DYNAMIC if is_dynamic else DEFAULT_TTL_ANALYSIS
        expires = datetime.utcnow() + ttl
        payload = {
            "tenant_id": tenant_id,
            "query": query,
            "response": response,
            "metadata": metadata or {},
            "expires_at_iso": expires.isoformat(),
        }
        qdrant, embedder = self._get_qdrant_and_embedder()
        if qdrant is not None:
            try:
                vec = embedder.encode(query)
                from qdrant_client.http import models as qm

                point_id = str(uuid.uuid4())
                qdrant.upsert(
                    collection_name=QDRANT_COLLECTION,
                    points=[qm.PointStruct(id=point_id, vector=vec.tolist(), payload=payload)],
                )
                return
            except Exception as e:  # noqa: BLE001
                logger.warning("语义缓存写入失败 → fallback sha256：%s", e)
        # fallback
        await self._set_sha256(tenant_id, query, payload, ttl)

    async def invalidate_by_keywords(self, tenant_id: str, keywords: list[str]) -> int:
        if not keywords:
            return 0
        qdrant, _ = self._get_qdrant_and_embedder()
        if qdrant is None:
            return await self._invalidate_sha256(tenant_id, keywords)
        # embedding 路径：扫该 tenant 全部 points，按 query 包含 keyword 删除
        try:
            from qdrant_client.http import models as qm

            offset = None
            deleted = 0
            while True:
                res, offset = qdrant.scroll(
                    collection_name=QDRANT_COLLECTION,
                    scroll_filter=qm.Filter(
                        must=[qm.FieldCondition(key="tenant_id", match=qm.MatchValue(value=tenant_id))]
                    ),
                    limit=100,
                    offset=offset,
                    with_payload=True,
                )
                ids_to_del: list[str] = []
                for p in res:
                    q = (p.payload or {}).get("query", "")
                    if any(kw in q for kw in keywords):
                        ids_to_del.append(p.id)
                if ids_to_del:
                    qdrant.delete(
                        collection_name=QDRANT_COLLECTION,
                        points_selector=qm.PointIdsList(points=ids_to_del),
                    )
                    deleted += len(ids_to_del)
                if offset is None:
                    break
            return deleted
        except Exception as e:  # noqa: BLE001
            logger.warning("语义缓存失效失败：%s", e)
            return 0

    def stats(self, tenant_id: str | None = None) -> dict[str, Any]:
        if tenant_id:
            d = self._stats.get(tenant_id, {"hits": 0, "misses": 0})
            total = d["hits"] + d["misses"]
            return {
                **d,
                "total": total,
                "hit_rate": (d["hits"] / total) if total else 0.0,
                "mode": self._mode,
                "threshold": SIMILARITY_THRESHOLD,
            }
        total_hits = sum(d["hits"] for d in self._stats.values())
        total_misses = sum(d["misses"] for d in self._stats.values())
        total = total_hits + total_misses
        return {
            "hits": total_hits,
            "misses": total_misses,
            "total": total,
            "hit_rate": (total_hits / total) if total else 0.0,
            "mode": self._mode,
            "threshold": SIMILARITY_THRESHOLD,
        }

    # ===== sha256 fallback（M2 行为，作为兜底）=====

    def _sha_key(self, tenant_id: str, query: str) -> str:
        h = hashlib.sha256(query.encode("utf-8")).hexdigest()[:24]
        return f"{self._namespace}:{tenant_id}:{h}"

    async def _get_sha256(self, tenant_id: str, query: str) -> dict[str, Any] | None:
        client = await self._get_redis()
        key = self._sha_key(tenant_id, query)
        raw = await client.get(key)
        if raw is None:
            self._stats[tenant_id]["misses"] += 1
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            await client.delete(key)
            self._stats[tenant_id]["misses"] += 1
            return None
        if payload.get("expires_at_iso"):
            try:
                if datetime.utcnow() > datetime.fromisoformat(payload["expires_at_iso"]):
                    await client.delete(key)
                    self._stats[tenant_id]["misses"] += 1
                    return None
            except ValueError:
                pass
        self._stats[tenant_id]["hits"] += 1
        return payload

    async def _set_sha256(
        self, tenant_id: str, query: str, payload: dict[str, Any], ttl: timedelta
    ) -> None:
        client = await self._get_redis()
        key = self._sha_key(tenant_id, query)
        await client.set(key, json.dumps(payload, ensure_ascii=False), ex=int(ttl.total_seconds()))

    async def _invalidate_sha256(self, tenant_id: str, keywords: list[str]) -> int:
        client = await self._get_redis()
        pattern = f"{self._namespace}:{tenant_id}:*"
        deleted = 0
        async for key in client.scan_iter(match=pattern):
            raw = await client.get(key)
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if any(kw in payload.get("query", "") for kw in keywords):
                await client.delete(key)
                deleted += 1
        return deleted


_cache: SemanticCache | None = None


def get_cache() -> SemanticCache:
    global _cache
    if _cache is None:
        _cache = SemanticCache()
    return _cache


def reset_cache() -> None:
    """测试用。"""
    global _cache
    _cache = None
