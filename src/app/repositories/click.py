import uuid
from datetime import datetime

import structlog
from sqlalchemy import func, select, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.click import ClickEvent

logger = structlog.get_logger()


class ClickRepository:
    """Database operations for ClickEvent model."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        link_id: uuid.UUID,
        ip_address: str | None = None,
        user_agent: str | None = None,
        referrer: str | None = None,
        clicked_at: datetime | None = None,
    ) -> ClickEvent:
        """Record a single click event."""
        event = ClickEvent(
            link_id=link_id,
            ip_address=ip_address,
            user_agent=user_agent,
            referrer=referrer,
        )
        if clicked_at:
            event.clicked_at = clicked_at
        self.db.add(event)
        await self.db.flush()
        return event

    async def bulk_create(self, events: list[dict]) -> int:
        """Batch-insert click events. Returns count inserted."""
        if not events:
            return 0
        objects = [
            ClickEvent(
                link_id=e["link_id"],
                ip_address=e.get("ip_address"),
                user_agent=e.get("user_agent"),
                referrer=e.get("referrer"),
                clicked_at=e.get("clicked_at"),
            )
            for e in events
        ]
        self.db.add_all(objects)
        await self.db.flush()
        logger.info("click_events_bulk_created", count=len(objects))
        return len(objects)

    async def get_daily_breakdown(
        self,
        link_id: uuid.UUID,
        days: int = 30,
    ) -> list[dict]:
        """Get click counts grouped by day for the last N days."""
        from datetime import timedelta, timezone
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        result = await self.db.execute(
            select(
                cast(ClickEvent.clicked_at, Date).label("date"),
                func.count().label("count"),
            )
            .where(
                ClickEvent.link_id == link_id,
                ClickEvent.clicked_at >= cutoff,
            )
            .group_by(cast(ClickEvent.clicked_at, Date))
            .order_by(cast(ClickEvent.clicked_at, Date))
        )
        return [
            {"date": str(row.date), "count": row.count}
            for row in result.all()
        ]

    async def get_top_referrers(
        self,
        link_id: uuid.UUID,
        limit: int = 10,
    ) -> list[dict]:
        """Get top referrers for a link."""
        result = await self.db.execute(
            select(
                ClickEvent.referrer,
                func.count().label("count"),
            )
            .where(
                ClickEvent.link_id == link_id,
                ClickEvent.referrer.isnot(None),
                ClickEvent.referrer != "",
            )
            .group_by(ClickEvent.referrer)
            .order_by(func.count().desc())
            .limit(limit)
        )
        return [
            {"referrer": row.referrer, "count": row.count}
            for row in result.all()
        ]

    async def get_top_user_agents(
        self,
        link_id: uuid.UUID,
        limit: int = 10,
    ) -> list[dict]:
        """Get top user agents for a link."""
        result = await self.db.execute(
            select(
                ClickEvent.user_agent,
                func.count().label("count"),
            )
            .where(
                ClickEvent.link_id == link_id,
                ClickEvent.user_agent.isnot(None),
                ClickEvent.user_agent != "",
            )
            .group_by(ClickEvent.user_agent)
            .order_by(func.count().desc())
            .limit(limit)
        )
        return [
            {"user_agent": row.user_agent, "count": row.count}
            for row in result.all()
        ]
