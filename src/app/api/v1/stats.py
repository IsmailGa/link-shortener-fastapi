import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
import io

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.click import LinkStatsResponse
from app.services.stats import StatsService

logger = structlog.get_logger()
router = APIRouter(tags=["Statistics"])


@router.get(
    "/links/{short_code}/stats/import_csv",
    summary="Import link statistics",
    response_class=StreamingResponse
)
async def import_csv_stats(
    short_code: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Import link statistics as CSV."""
    service = StatsService(db)
    try:
        csv_data = await service.import_csv_stats(
            short_code=short_code,
            user_id=user.id,
        )
        
        if isinstance(csv_data, str):
            csv_data = csv_data.encode("utf-8")
        
        return StreamingResponse(
            io.BytesIO(csv_data),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=stats_{short_code}.csv"}
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


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