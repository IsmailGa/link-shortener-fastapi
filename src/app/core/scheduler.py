import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings

logger = structlog.get_logger()

scheduler = AsyncIOScheduler()


def setup_scheduler(cleanup_func) -> None:
    """Configure the scheduler with cleanup job.

    Args:
        cleanup_func: Async callable that performs stale link cleanup.
    """
    scheduler.add_job(
        cleanup_func,
        CronTrigger(
            hour=settings.cleanup_cron_hour,
            minute=settings.cleanup_cron_minute,
        ),
        id="cleanup_stale_links",
        replace_existing=True,
        misfire_grace_time=3600,  # Allow 1 hour grace for misfired jobs
    )
    logger.info(
        "scheduler_configured",
        job="cleanup_stale_links",
        cron=f"{settings.cleanup_cron_minute} {settings.cleanup_cron_hour} * * *",
    )
