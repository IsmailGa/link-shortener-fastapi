import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.click import ClickRepository
from app.repositories.link import LinkRepository

logger = structlog.get_logger()


class StatsService:
    """Aggregates and returns link statistics."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.link_repo = LinkRepository(db)
        self.click_repo = ClickRepository(db)

    async def get_link_stats(
        self,
        short_code: str,
        user_id: uuid.UUID,
    ) -> dict:
        """Get comprehensive statistics for a link.
        
        Only the link owner can view stats.
        
        Raises:
            ValueError: If link not found or not owned by user.
        """
        link = await self.link_repo.get_by_short_code(short_code)
        if not link:
            raise ValueError("Link not found")
        if link.owner_id != user_id:
            raise ValueError("Not authorized to view stats for this link")

        # Fetch all stats concurrently
        daily_clicks = await self.click_repo.get_daily_breakdown(link.id)
        top_referrers = await self.click_repo.get_top_referrers(link.id)
        top_user_agents = await self.click_repo.get_top_user_agents(link.id)

        return {
            "short_code": link.short_code,
            "original_url": link.original_url,
            "total_clicks": link.click_count,
            "created_at": link.created_at,
            "last_clicked_at": link.last_clicked_at,
            "daily_clicks": daily_clicks,
            "top_referrers": top_referrers,
            "top_user_agents": top_user_agents,
        }
