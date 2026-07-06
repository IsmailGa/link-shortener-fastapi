import uuid
from datetime import datetime

import structlog
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.rabbitmq import rabbitmq_manager
from app.core.short_code import generate_short_code
from app.repositories.link import LinkRepository

logger = structlog.get_logger()

# Redis cache TTL for resolved URLs (1 hour)
_CACHE_TTL = 3600


class LinkService:
    """Business logic for link creation, resolution, and management."""

    def __init__(self, db: AsyncSession, redis: Redis) -> None:
        self.db = db
        self.redis = redis
        self.link_repo = LinkRepository(db)

    async def create_link(
        self,
        url: str,
        custom_alias: str | None = None,
        owner_id: uuid.UUID | None = None,
        creator_ip: str | None = None,
        expires_at: datetime | None = None,
    ) -> dict:
        """Create a shortened link.
        
        Args:
            url: The original URL to shorten.
            custom_alias: Optional user-chosen short code.
            owner_id: UUID of authenticated user (None for anonymous).
            creator_ip: IP address for anonymous rate-limit tracking.
            expires_at: Optional expiration datetime.
        
        Raises:
            ValueError: If custom alias is already taken.
        """
        if custom_alias:
            # Check if alias is available
            if await self.link_repo.short_code_exists(custom_alias):
                raise ValueError(f"Short code '{custom_alias}' is already taken")
            short_code = custom_alias
        else:
            short_code = await generate_short_code(self.redis)

        link = await self.link_repo.create(
            short_code=short_code,
            original_url=str(url),
            owner_id=owner_id,
            creator_ip=creator_ip,
            expires_at=expires_at,
        )

        # Pre-populate Redis cache
        await self.redis.set(
            f"short:{short_code}",
            link.original_url,
            ex=_CACHE_TTL,
        )

        await self.db.commit()

        return {
            "id": link.id,
            "short_code": link.short_code,
            "original_url": link.original_url,
            "short_url": f"{settings.base_url}/{link.short_code}",
            "click_count": link.click_count,
            "is_active": link.is_active,
            "created_at": link.created_at,
            "expires_at": link.expires_at,
        }

    async def resolve_and_redirect(
        self,
        short_code: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
        referrer: str | None = None,
    ) -> str:
        """Resolve a short code to its original URL.
        
        1. Check Redis cache
        2. On cache miss, query DB and populate cache
        3. Publish click event to RabbitMQ (fire-and-forget)
        
        Raises:
            ValueError: If short code not found or link is inactive/expired.
        """
        # Step 1: Check Redis cache
        cached_url = await self.redis.get(f"short:{short_code}")

        if cached_url:
            logger.debug("cache_hit", short_code=short_code)
            original_url = cached_url
            # We still need the link_id for click tracking
            link = await self.link_repo.get_by_short_code(short_code)
            link_id = str(link.id) if link else None
        else:
            # Step 2: Cache miss — query DB
            logger.debug("cache_miss", short_code=short_code)
            link = await self.link_repo.get_by_short_code(short_code)

            if link is None:
                raise ValueError("Link not found")

            # Check expiration
            if link.expires_at and link.expires_at < datetime.now(link.expires_at.tzinfo):
                raise ValueError("Link has expired")

            original_url = link.original_url
            link_id = str(link.id)

            # Populate cache
            await self.redis.set(
                f"short:{short_code}",
                original_url,
                ex=_CACHE_TTL,
            )

        # Step 3: Publish click event (fire-and-forget)
        if link_id:
            await rabbitmq_manager.publish_click_event(
                link_id=link_id,
                short_code=short_code,
                ip_address=ip_address,
                user_agent=user_agent,
                referrer=referrer,
            )

        return original_url

    async def get_user_links(
        self,
        user_id: uuid.UUID,
        page: int = 1,
        size: int = 20,
    ) -> dict:
        """Get paginated links for an authenticated user."""
        offset = (page - 1) * size
        links, total = await self.link_repo.get_user_links(
            user_id=user_id,
            offset=offset,
            limit=size,
        )

        pages = (total + size - 1) // size  # Ceiling division

        return {
            "items": [
                {
                    "id": link.id,
                    "short_code": link.short_code,
                    "original_url": link.original_url,
                    "short_url": f"{settings.base_url}/{link.short_code}",
                    "click_count": link.click_count,
                    "is_active": link.is_active,
                    "created_at": link.created_at,
                    "expires_at": link.expires_at,
                }
                for link in links
            ],
            "total": total,
            "page": page,
            "size": size,
            "pages": pages,
        }

    async def delete_link(
        self,
        short_code: str,
        user_id: uuid.UUID,
    ) -> bool:
        """Soft-delete a link owned by the user.
        
        Raises:
            ValueError: If link not found or not owned by user.
        """
        link = await self.link_repo.get_by_short_code(short_code)
        if not link:
            raise ValueError("Link not found")
        if link.owner_id != user_id:
            raise ValueError("Not authorized to delete this link")

        deleted = await self.link_repo.soft_delete(
            link_id=link.id, owner_id=user_id
        )

        if deleted:
            # Invalidate cache
            await self.redis.delete(f"short:{short_code}")
            await self.db.commit()

        return deleted
