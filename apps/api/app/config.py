"""应用配置：通过 pydantic-settings 读 env / .env。

设计：
- 所有 secret / 环境差异参数通过环境变量注入
- 一份 Settings 对象贯穿请求生命周期
- 只在启动时读一次 .env
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ===== App =====
    sidekick_env: str = "development"
    sidekick_log_level: str = "INFO"

    # ===== 数据库 =====
    database_url: str = "postgresql://sidekick:sidekick@localhost:5433/sidekick"

    # ===== Redis =====
    redis_url: str = "redis://localhost:6380/0"

    # ===== Qdrant =====
    qdrant_url: str = "http://localhost:6333"

    # ===== Langfuse =====
    langfuse_host: str = "http://localhost:3030"
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None

    # ===== Shopify (单租户兜底；多租户走 config/tenants.yaml) =====
    shopify_shop_domain: str | None = None
    shopify_admin_token: str | None = None
    shopify_api_version: str = "2025-10"

    # ===== 模型 keys（暴露用于 LiteLLM）=====
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    dashscope_api_key: str | None = None
    zhipu_api_key: str | None = None

    # ===== Agent =====
    agent_max_iterations: int = 15
    default_model: str = "dashscope:qwen-plus"

    @property
    def is_production(self) -> bool:
        return self.sidekick_env == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
