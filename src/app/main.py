from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.redirect import router as redirect_router
from app.api.v1.router import api_v1_router
from app.config import settings
from app.core.rabbitmq import rabbitmq_manager
from app.core.redis import redis_manager
from app.core.scheduler import scheduler, setup_scheduler
from app.db.session import engine
from app.exceptions import register_exception_handlers
from app.logging_config import configure_logging
from app.middleware.request_id import RequestIDMiddleware
from app.services.cleanup import cleanup_stale_links

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown.
    
    Startup:
        - Configure structured logging
        - Connect to Redis
        - Connect to RabbitMQ
        - Start APScheduler for cleanup tasks
    
    Shutdown:
        - Stop scheduler
        - Disconnect from RabbitMQ
        - Disconnect from Redis
        - Dispose database engine
    """
    # --- Startup ---
    configure_logging(
        json_logs=settings.is_production,
        log_level="DEBUG" if settings.debug else "INFO",
    )
    logger.info(
        "app_starting",
        app_name=settings.app_name,
        environment=settings.app_env,
    )

    # Connect to services
    await redis_manager.connect()
    await rabbitmq_manager.connect()

    # Setup and start scheduler
    setup_scheduler(cleanup_stale_links)
    scheduler.start()

    logger.info("app_started")

    yield

    # --- Shutdown ---
    logger.info("app_shutting_down")

    scheduler.shutdown(wait=False)
    await rabbitmq_manager.disconnect()
    await redis_manager.disconnect()
    await engine.dispose()

    logger.info("app_shutdown_complete")


def create_app() -> FastAPI:
    """Application factory."""
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/api/docs" if not settings.is_production else None,
        redoc_url="/api/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # Middleware (order matters — outermost first)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Restrict in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIDMiddleware)

    # Exception handlers
    register_exception_handlers(app)

    # Routers
    app.include_router(api_v1_router)
    app.include_router(redirect_router)  # Root-level redirect /{code}

    return app


# Module-level app instance for Gunicorn/Uvicorn
app = create_app()
