"""Configuration via environment variables (12-factor)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    app_name: str = "ChannelTruth"
    version: str = "1.0.0"
    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///./channeltruth.db")
    )
    #: Demo mode lets the bundled dashboard pick a tenant with `X-Account-Id`.
    #: Never enable it on the public internet.
    demo_mode: bool = field(default_factory=lambda: _bool("CHANNELTRUTH_DEMO", True))
    seed_demo_data: bool = field(default_factory=lambda: _bool("CHANNELTRUTH_SEED", True))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))

    #: Default lookback: how far before a conversion a touch still gets credit.
    #: 30 days is the common ad-platform default; 7 is typical for display.
    lookback_days: int = field(default_factory=lambda: _int("ATTRIBUTION_LOOKBACK_DAYS", 30))
    #: Time-decay half-life in days. 7 means a touch a week old is worth half.
    half_life_days: float = field(
        default_factory=lambda: float(os.getenv("ATTRIBUTION_HALF_LIFE_DAYS", "7"))
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
