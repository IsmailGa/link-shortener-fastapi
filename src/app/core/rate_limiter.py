import time

import structlog
from redis.asyncio import Redis

from app.config import settings

logger = structlog.get_logger()

# Lua script for atomic sliding window rate limiting
# Uses a sorted set where scores are timestamps
_LUA_SLIDING_WINDOW = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])

-- Remove entries outside the window
redis.call("ZREMRANGEBYSCORE", key, 0, now - window)

-- Count remaining entries
local count = redis.call("ZCARD", key)

if count < limit then
    -- Add this request with unique member (timestamp:random)
    redis.call("ZADD", key, now, tostring(now) .. ":" .. tostring(math.random(1000000)))
    redis.call("EXPIRE", key, window)
    return {1, limit - count - 1}
else
    redis.call("EXPIRE", key, window)
    return {0, 0}
end
"""


class RateLimiter:
    """Sliding window rate limiter backed by Redis sorted sets."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def check_rate_limit(
        self,
        identifier: str,
        limit: int = settings.anon_rate_limit_per_day,
        window_seconds: int = 86400,
    ) -> tuple[bool, int]:
        """Check if the identifier is within the rate limit.

        Args:
            identifier: The key to rate limit (e.g., IP address).
            limit: Maximum number of requests in the window.
            window_seconds: Size of the sliding window in seconds.

        Returns:
            Tuple of (is_allowed, remaining_requests).
        """
        key = f"ratelimit:create:{identifier}"
        now = int(time.time())

        result = await self._redis.eval(
            _LUA_SLIDING_WINDOW, 1, key, now, window_seconds, limit
        )

        is_allowed = bool(result[0])
        remaining = int(result[1])

        logger.debug(
            "rate_limit_checked",
            identifier=identifier,
            allowed=is_allowed,
            remaining=remaining,
        )
        return is_allowed, remaining
