"""Celery 入口：Redis broker + result backend。

启动（macOS 必须 solo pool + 关 fork safety；prefork 会因 httpx/SSL fork-unsafe 触发 SIGSEGV）：
    OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES uv run celery -A worker.celery_app worker -l info --pool=solo

Linux 生产环境可以用 prefork：
    uv run celery -A worker.celery_app worker -l info -c 4

任务模块见 worker.tasks。
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
if (ROOT / ".env").exists():
    load_dotenv(ROOT / ".env")

from celery import Celery  # noqa: E402

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6380/0")

celery_app = Celery(
    "sidekick",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    task_time_limit=600,  # 10 分钟硬上限
    result_expires=3600,
)
