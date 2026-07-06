import time

import structlog
from fastapi import APIRouter
from sqlalchemy import text

from app.core.rabbitmq import rabbitmq_manager
from app.core.redis import redis_manager
from app.db.session import engine
from app.schemas.health import HealthResponse, ReadinessResponse, ServiceStatus

logger = structlog.get_logger()
router = APIRouter(prefix="/health", tags=["Health"])


@router.get("", response_model=HealthResponse)
async def liveness():
    """Liveness probe — confirms the app process is running."""
    return HealthResponse()


@router.get("/ready", response_model=ReadinessResponse)
async def readiness():
    """Readiness probe — checks all service dependencies."""
    services: list[ServiceStatus] = []

    # Check PostgreSQL
    try:
        start = time.monotonic()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        latency = (time.monotonic() - start) * 1000
        services.append(ServiceStatus(name="postgresql", status="ok", latency_ms=round(latency, 2)))
    except Exception as e:
        services.append(ServiceStatus(name="postgresql", status="error", error=str(e)))

    # Check Redis
    try:
        start = time.monotonic()
        await redis_manager.client.ping()
        latency = (time.monotonic() - start) * 1000
        services.append(ServiceStatus(name="redis", status="ok", latency_ms=round(latency, 2)))
    except Exception as e:
        services.append(ServiceStatus(name="redis", status="error", error=str(e)))

    # Check RabbitMQ
    try:
        rmq_status = "ok" if rabbitmq_manager._connection and not rabbitmq_manager._connection.is_closed else "error"
        services.append(ServiceStatus(name="rabbitmq", status=rmq_status))
    except Exception as e:
        services.append(ServiceStatus(name="rabbitmq", status="error", error=str(e)))

    overall = "ok" if all(s.status == "ok" for s in services) else "degraded"
    return ReadinessResponse(status=overall, services=services)
