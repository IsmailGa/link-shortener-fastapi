import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.security import decode_access_token
from app.models.link import Link
from app.models.user import User


@pytest.mark.asyncio
async def test_auth_flow(client: AsyncClient):
    """Test user registration, login, and token refresh."""
    email = f"test_{uuid.uuid4().hex[:6]}@example.com"
    password = "supersecurepassword123"

    reg_resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert reg_resp.status_code == 201
    tokens = reg_resp.json()
    assert "access_token" in tokens
    assert "refresh_token" in tokens
    assert tokens["token_type"] == "bearer"

    payload = decode_access_token(tokens["access_token"])
    assert "sub" in payload

    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_resp.status_code == 200
    login_tokens = login_resp.json()
    assert "access_token" in login_tokens
    assert "refresh_token" in login_tokens

    refresh_resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": login_tokens["refresh_token"]},
    )
    assert refresh_resp.status_code == 200
    new_tokens = refresh_resp.json()
    assert "access_token" in new_tokens
    assert "refresh_token" in new_tokens


@pytest.mark.asyncio
async def test_anonymous_shorten_and_redirect(client: AsyncClient):
    """Test shortening a link anonymously and redirecting."""
    original_url = "https://example.com/some/long/path/to/resource"

    resp = await client.post(
        "/api/v1/links",
        json={"url": original_url},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "short_code" in data
    assert data["original_url"] == original_url
    assert "short_url" in data
    assert data["click_count"] == 0

    short_code = data["short_code"]

    redir_resp = await client.get(f"/{short_code}", follow_redirects=False)
    assert redir_resp.status_code == 307
    assert redir_resp.headers["location"] == original_url


@pytest.mark.asyncio
async def test_custom_alias(client: AsyncClient):
    """Test custom aliases and duplicate collision."""
    alias = f"mycustomalias_{uuid.uuid4().hex[:6]}"
    url1 = "https://google.com"
    url2 = "https://yahoo.com"

    resp1 = await client.post(
        "/api/v1/links",
        json={"url": url1, "custom_alias": alias},
    )
    assert resp1.status_code == 201
    assert resp1.json()["short_code"] == alias

    resp2 = await client.post(
        "/api/v1/links",
        json={"url": url2, "custom_alias": alias},
    )
    assert resp2.status_code == 409
    assert "already taken" in resp2.json()["error"]


@pytest.mark.asyncio
async def test_anonymous_rate_limiting(client: AsyncClient):
    """Test that anonymous users are rate limited.
    
    We mock or check the rate limiter logic or perform multiple requests
    if the rate limit is low. Since limit is 50, we can temporarily mock
    the rate limiter checking logic to test the behavior when limit is hit.
    """
    from app.core.rate_limiter import RateLimiter
    from unittest.mock import AsyncMock, patch

    with patch.object(RateLimiter, "check_rate_limit", AsyncMock(return_value=(False, 0))):
        resp = await client.post(
            "/api/v1/links",
            json={"url": "https://wikipedia.org"},
        )
        assert resp.status_code == 429
        assert "Rate limit exceeded" in resp.json()["error"]


@pytest.mark.asyncio
async def test_authenticated_shorten_and_stats(client: AsyncClient):
    """Test shortening links as authenticated user and accessing statistics."""
    email = f"stats_user_{uuid.uuid4().hex[:6]}@example.com"
    password = "superpassword123"
    reg_resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    token = reg_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    url = "https://github.com/google"
    create_resp = await client.post(
        "/api/v1/links",
        json={"url": url},
        headers=headers,
    )
    assert create_resp.status_code == 201
    link_data = create_resp.json()
    short_code = link_data["short_code"]
    stats_resp = await client.get(
        f"/api/v1/links/{short_code}/stats",
        headers=headers,
    )
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert stats["short_code"] == short_code
    assert stats["total_clicks"] == 0
    assert len(stats["daily_clicks"]) == 0
    anon_stats_resp = await client.get(f"/api/v1/links/{short_code}/stats")
    assert anon_stats_resp.status_code == 401


@pytest.mark.asyncio
async def test_cleanup_stale_links():
    """Test the periodic cleanup task.
    
    Verifies that:
    1. Anonymous links inactive for >30 days are soft-deleted (is_active=False).
    2. Fresh anonymous links remain active.
    3. Stale authenticated links remain active (exempt from cleanup).
    """
    from datetime import datetime, timedelta, timezone
    from app.db.session import async_session_factory
    from app.models.link import Link
    from app.models.user import User
    from app.services.cleanup import cleanup_stale_links
    from sqlalchemy import select

    async with async_session_factory() as session:
        owner = User(email="owner@example.com", hashed_password="hashed_password")
        session.add(owner)
        await session.flush()

        stale_anon = Link(
            short_code="staleanon",
            original_url="https://example.com/stale-anon",
            created_at=datetime.now(timezone.utc) - timedelta(days=31),
            last_clicked_at=None,
        )
        fresh_anon = Link(
            short_code="freshanon",
            original_url="https://example.com/fresh-anon",
            created_at=datetime.now(timezone.utc) - timedelta(days=1),
            last_clicked_at=None,
        )
        stale_auth = Link(
            short_code="staleauth",
            original_url="https://example.com/stale-auth",
            owner_id=owner.id,
            created_at=datetime.now(timezone.utc) - timedelta(days=31),
            last_clicked_at=None,
        )
        
        session.add_all([stale_anon, fresh_anon, stale_auth])
        await session.commit()

    await cleanup_stale_links()

    async with async_session_factory() as session:
        stmt = select(Link).order_by(Link.short_code)
        res = await session.execute(stmt)
        links = res.scalars().all()
        
        links_dict = {l.short_code: l.is_active for l in links}
        
        assert links_dict["staleanon"] is False
        assert links_dict["freshanon"] is True
        assert links_dict["staleauth"] is True
