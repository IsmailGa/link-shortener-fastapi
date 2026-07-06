import structlog
from redis.asyncio import ConnectionPool, Redis

from app.config import settings

logger = structlog.get_logger()


class RedisManager:
    """Manages Redis connection pool lifecycle."""

    def __init__(self) -> None:
        self._pool: ConnectionPool | None = None
        self._redis: Redis | None = None

    async def connect(self) -> None:
        """Initialize the Redis connection pool."""
        self._pool = ConnectionPool.from_url(
            settings.redis_url,
            decode_responses=True,
            max_connections=50,
        )
        self._redis = Redis(connection_pool=self._pool)
        # Verify connectivity
        await self._redis.ping()
        logger.info("redis_connected", url=settings.redis_url)

    async def disconnect(self) -> None:
        """Close the Redis connection pool."""
        if self._redis:
            await self._redis.close()
        if self._pool:
            await self._pool.disconnect()
        logger.info("redis_disconnected")

    @property
    def client(self) -> Redis:
        """Get the Redis client instance."""
        if self._redis is None:
            raise RuntimeError("Redis is not connected. Call connect() first.")
        return self._redis


redis_manager = RedisManager()
