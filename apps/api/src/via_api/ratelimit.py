"""Fixed-window rate limiting backed by Redis.

Used on authentication endpoints. If Redis is unavailable the limiter fails
*open* (requests are allowed and a warning is logged): an outage of the rate
limit store must not lock every user out. Readiness reports Redis failures.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from redis import Redis
from redis.exceptions import RedisError

from via_api.errors import APIError

logger = logging.getLogger("via_api.ratelimit")


@dataclass(frozen=True)
class Limit:
    name: str
    max_requests: int
    window_seconds: int


LOGIN_PER_IP = Limit("login-ip", 20, 60)
LOGIN_PER_ACCOUNT = Limit("login-account", 8, 300)
REGISTER_PER_IP = Limit("register-ip", 10, 3600)
PASSWORD_RESET_PER_IP = Limit("reset-ip", 5, 3600)
PASSWORD_CHANGE_PER_USER = Limit("password-change-user", 10, 3600)
MEMBER_LOOKUP_PER_USER = Limit("member-lookup-user", 30, 3600)
ANALYSES_PER_USER = Limit("analysis-user", 60, 3600)
AI_REQUESTS_PER_USER = Limit("ai-user", 30, 3600)


class RateLimiter:
    def __init__(self, redis: Redis, enabled: bool = True) -> None:
        self.redis = redis
        self.enabled = enabled

    def hit(self, limit: Limit, key: str) -> None:
        """Count one request; raise 429 when the window's budget is exhausted."""
        if not self.enabled:
            return
        redis_key = f"via:rl:{limit.name}:{key}"
        try:
            pipe = self.redis.pipeline()
            pipe.incr(redis_key)
            pipe.expire(redis_key, limit.window_seconds, nx=True)
            count, _ = pipe.execute()
            ttl = self.redis.ttl(redis_key) if count > limit.max_requests else 0
        except RedisError:
            logger.warning("Rate limiter unavailable; allowing request", extra={"limit": limit.name})
            return
        if count > limit.max_requests:
            raise APIError(
                429,
                "rate_limited",
                "Too many attempts. Please wait and try again.",
                {"retry_after_seconds": max(int(ttl), 1)},
            )
