import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.click import LinkStatsResponse
from app.services.stats import StatsService

logger = structlog.get_logger()
router = APIRouter(tags=["Statistics"])


@router.get(
    "/links/{short_code}/stats",
    response_model=LinkStatsResponse,
    summary="Get link statistics",
)
async def get_link_stats(
    short_code: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get comprehensive statistics for a link (owner only).

    Includes total clicks, daily breakdown, top referrers, and top user agents.
    """
    service = StatsService(db)
    try:
        return await service.get_link_stats(
            short_code=short_code,
            user_id=user.id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
