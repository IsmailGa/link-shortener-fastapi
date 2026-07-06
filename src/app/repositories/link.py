import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.link import Link

logger = structlog.get_logger()


class LinkRepository:
    """Database operations for Link model."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        short_code: str,
        original_url: str,
        owner_id: uuid.UUID | None = None,
        creator_ip: str | None = None,
        expires_at: datetime | None = None,
    ) -> Link:
        """Create a new shortened link."""
        link = Link(
            short_code=short_code,
            original_url=original_url,
            owner_id=owner_id,
            creator_ip=creator_ip,
            expires_at=expires_at,
        )
        self.db.add(link)
        await self.db.flush()
        await self.db.refresh(link)
        logger.info("link_created", short_code=short_code, owner_id=str(owner_id))
        return link

    async def get_by_short_code(self, code: str) -> Link | None:
        """Fetch a link by its short code. Hot path for redirects."""
        result = await self.db.execute(
            select(Link).where(
                Link.short_code == code,
                Link.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, link_id: uuid.UUID) -> Link | None:
        """Fetch a link by its UUID."""
        result = await self.db.execute(
            select(Link).where(Link.id == link_id)
        )
        return result.scalar_one_or_none()

    async def get_user_links(
        self,
        user_id: uuid.UUID,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[Link], int]:
        """Fetch paginated links for a user.
        
        Returns:
            Tuple of (links, total_count).
        """
        # Count query
        count_result = await self.db.execute(
            select(func.count()).select_from(Link).where(
                Link.owner_id == user_id,
                Link.is_active.is_(True),
            )
        )
        total = count_result.scalar_one()

        # Data query
        result = await self.db.execute(
            select(Link)
            .where(
                Link.owner_id == user_id,
                Link.is_active.is_(True),
            )
            .order_by(Link.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        links = list(result.scalars().all())
        return links, total

    async def increment_click_count(self, link_id: uuid.UUID) -> None:
        """Atomically increment the click counter and update last_clicked_at."""
        await self.db.execute(
            update(Link)
            .where(Link.id == link_id)
            .values(
                click_count=Link.click_count + 1,
                last_clicked_at=datetime.now(timezone.utc),
            )
        )

    async def short_code_exists(self, code: str) -> bool:
        """Check if a short code already exists."""
        result = await self.db.execute(
            select(Link.id).where(Link.short_code == code)
        )
        return result.scalar_one_or_none() is not None

    async def soft_delete(self, link_id: uuid.UUID, owner_id: uuid.UUID) -> bool:
        """Soft-delete a link (set is_active=False). Returns True if found and deleted."""
        result = await self.db.execute(
            update(Link)
            .where(
                Link.id == link_id,
                Link.owner_id == owner_id,
                Link.is_active.is_(True),
            )
            .values(is_active=False)
        )
        if result.rowcount > 0:
            logger.info("link_soft_deleted", link_id=str(link_id))
            return True
        return False

    async def get_stale_links(self, inactive_days: int) -> list[Link]:
        """Find links not clicked in the last N days (for cleanup)."""
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=inactive_days)
        result = await self.db.execute(
            select(Link).where(
                Link.is_active.is_(True),
                Link.owner_id.is_(None),  # Only cleanup anonymous links
                (
                    (Link.last_clicked_at < cutoff) |
                    (
                        Link.last_clicked_at.is_(None) &
                        (Link.created_at < cutoff)
                    )
                ),
            )
        )
        return list(result.scalars().all())

    async def bulk_deactivate(self, link_ids: list[uuid.UUID]) -> int:
        """Deactivate multiple links at once. Returns count deactivated."""
        if not link_ids:
            return 0
        result = await self.db.execute(
            update(Link)
            .where(Link.id.in_(link_ids))
            .values(is_active=False)
        )
        return result.rowcount
