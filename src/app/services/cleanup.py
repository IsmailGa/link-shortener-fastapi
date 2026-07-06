import structlog

from app.config import settings
from app.db.session import async_session_factory
from app.repositories.link import LinkRepository
from app.repositories.refresh_token import RefreshTokenRepository

logger = structlog.get_logger()


async def cleanup_stale_links() -> None:
    """Scheduled task: deactivate anonymous links inactive for N days.
    
    Uses a Redis distributed lock to prevent duplicate execution
    across multiple app replicas.
    """
    from app.core.redis import redis_manager

    redis = redis_manager.client
    lock = redis.lock("cleanup:stale_links:lock", timeout=300)

    acquired = await lock.acquire(blocking=False)
    if not acquired:
        logger.info("cleanup_skipped", reason="another_instance_running")
        return

    try:
        async with async_session_factory() as session:
            link_repo = LinkRepository(session)
            token_repo = RefreshTokenRepository(session)

            # Cleanup stale anonymous links
            stale_links = await link_repo.get_stale_links(
                inactive_days=settings.link_inactive_days
            )

            if stale_links:
                link_ids = [link.id for link in stale_links]
                deactivated = await link_repo.bulk_deactivate(link_ids)

                # Invalidate cached URLs
                for link in stale_links:
                    await redis.delete(f"short:{link.short_code}")

                logger.info(
                    "stale_links_cleaned",
                    found=len(stale_links),
                    deactivated=deactivated,
                )
            else:
                logger.info("stale_links_cleaned", found=0, deactivated=0)

            # Also cleanup expired refresh tokens
            expired_tokens = await token_repo.cleanup_expired()
            if expired_tokens:
                logger.info("expired_tokens_cleaned", count=expired_tokens)

            await session.commit()

    except Exception:
        logger.exception("cleanup_failed")
    finally:
        try:
            await lock.release()
        except Exception:
            pass  # Lock may have expired
