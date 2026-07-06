import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limiter import RateLimiter
from app.dependencies import get_client_ip, get_current_user, get_db, get_optional_user, get_redis
from app.exceptions import RateLimitExceededError
from app.models.user import User
from app.schemas.link import LinkCreate, LinkListResponse, LinkResponse
from app.services.link import LinkService

logger = structlog.get_logger()
router = APIRouter(tags=["Links"])


@router.post(
    "/links",
    response_model=LinkResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a short link",
)
async def create_link(
    body: LinkCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    user: User | None = Depends(get_optional_user),
):
    """Create a shortened URL.

    - Authenticated users: unlimited link creation.
    - Anonymous users: limited to 50 per day (by IP).
    """
    client_ip = get_client_ip(request)

    # Rate limit anonymous users
    if user is None:
        rate_limiter = RateLimiter(redis)
        allowed, remaining = await rate_limiter.check_rate_limit(client_ip)
        if not allowed:
            raise RateLimitExceededError(remaining=remaining)

    service = LinkService(db, redis)
    try:
        result = await service.create_link(
            url=str(body.url),
            custom_alias=body.custom_alias,
            owner_id=user.id if user else None,
            creator_ip=client_ip if user is None else None,
            expires_at=body.expires_at,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    return result


@router.get(
    "/links",
    response_model=LinkListResponse,
    summary="List user's links",
)
async def list_links(
    page: int = 1,
    size: int = 20,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    user: User = Depends(get_current_user),
):
    """List all links created by the authenticated user (paginated)."""
    service = LinkService(db, redis)
    return await service.get_user_links(
        user_id=user.id,
        page=max(1, page),
        size=min(max(1, size), 100),  # Clamp between 1-100
    )


@router.delete(
    "/links/{short_code}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a link",
)
async def delete_link(
    short_code: str,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    user: User = Depends(get_current_user),
):
    """Soft-delete a link owned by the authenticated user."""
    service = LinkService(db, redis)
    try:
        await service.delete_link(short_code=short_code, user_id=user.id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
