"""Pydantic-settings driven configuration.

All values are env-driven (`VEDIX_*`). Defaults are SQLite-in-memory +
fake redis so the test suite never spins up a real database. Production
docker-compose injects `VEDIX_POSTGRES_URL` and `VEDIX_REDIS_URL`.
"""
from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VEDIX_",
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
    )

    # ----- core -----
    env: Literal["dev", "test", "prod"] = "test"
    log_level: str = "INFO"

    # ----- storage -----
    # tests default to in-memory SQLite via aiosqlite
    postgres_url: str = "sqlite+aiosqlite:///:memory:"
    redis_url: str = "redis://localhost:6379/0"

    # ----- auth -----
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 60 * 24

    # ----- payment provider secrets -----
    yukassa_secret: str = "yukassa-test-secret"
    stripe_secret: str = "stripe-test-secret"
    stripe_webhook_secret: str = "whsec_test"
    cloudpayments_secret: str = "cp-test-secret"
    boosty_secret: str = "boosty-test-secret"
    crypto_wallet_trc20: str = ""

    # ----- runtime -----
    job_workspace_root: str = "./.vedix-jobs"


settings = Settings()
