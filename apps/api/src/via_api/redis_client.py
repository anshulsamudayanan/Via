"""Shared Redis client (job queue from CP4, rate limiting from CP3)."""

from __future__ import annotations

from functools import lru_cache

from redis import Redis

from via_api.config import get_settings


@lru_cache
def get_redis() -> Redis:
    return Redis.from_url(get_settings().redis_url, socket_connect_timeout=3, socket_timeout=3)
