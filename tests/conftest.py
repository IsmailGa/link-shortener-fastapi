import asyncio
import pytest
from httpx import AsyncClient, ASGITransport
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import async_session_factory
from app.main import app


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
async def clean_redis():
    """Clear Redis between tests using an independent connection."""
    r = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        await r.flushdb()
    finally:
        await r.close()


@pytest.fixture(autouse=True)
async def clean_db():
    """Truncate all PostgreSQL tables between tests to ensure isolation."""
    async with async_session_factory() as session:
        await session.execute(
            text("TRUNCATE TABLE users, links, refresh_tokens, click_events CASCADE;")
        )
        await session.commit()


@pytest.fixture
async def db_session() -> AsyncSession:
    """Provide a transactional database session."""
    async with async_session_factory() as session:
        async with session.begin():
            yield session
            await session.rollback()


@pytest.fixture
async def client() -> AsyncClient:
    """Async HTTP client for testing endpoints, wrapped in lifespan context."""
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac
