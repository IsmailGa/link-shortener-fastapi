import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_client_ip, get_db, get_redis
from app.exceptions import LinkNotFoundError
from app.services.link import LinkService

logger = structlog.get_logger()
router = APIRouter(tags=["Redirect"])


@router.get(
    "/{short_code}",
    summary="Redirect to original URL",
    response_class=RedirectResponse,
    status_code=307,
)
async def redirect_to_url(
    short_code: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """Resolve a short code and redirect to the original URL.

    Uses 307 Temporary Redirect so browsers don't cache the redirect
    (important for click analytics).
    """
    client_ip = get_client_ip(request)
    user_agent = request.headers.get("User-Agent")
    referrer = request.headers.get("Referer")

    service = LinkService(db, redis)
    try:
        original_url = await service.resolve_and_redirect(
            short_code=short_code,
            ip_address=client_ip,
            user_agent=user_agent,
            referrer=referrer,
        )
    except ValueError:
        raise LinkNotFoundError(short_code=short_code)

    return RedirectResponse(url=original_url, status_code=307)
