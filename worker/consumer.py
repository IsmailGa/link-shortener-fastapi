"""RabbitMQ click event consumer worker.

Runs as a separate process/container. Consumes click events
from the queue and writes them to PostgreSQL in batches.
"""
import asyncio
import json
import uuid
from datetime import datetime

import aio_pika
import structlog

from app.config import settings
from app.db.session import async_session_factory, engine
from app.logging_config import configure_logging
from app.repositories.click import ClickRepository
from app.repositories.link import LinkRepository

logger = structlog.get_logger()

# Batch settings
BATCH_SIZE = 100
FLUSH_INTERVAL = 5.0  # seconds


class ClickEventConsumer:
    """Consumes click events from RabbitMQ and writes to DB in batches."""

    def __init__(self) -> None:
        self._buffer: list[dict] = []
        self._flush_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Connect to RabbitMQ and start consuming."""
        configure_logging(
            json_logs=settings.is_production,
            log_level="DEBUG" if settings.debug else "INFO",
        )
        logger.info("consumer_starting")

        connection = await aio_pika.connect_robust(settings.rabbitmq_url)
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=BATCH_SIZE)

        queue = await channel.declare_queue(
            "click_statistics",
            durable=True,
        )

        # Start periodic flush
        self._flush_task = asyncio.create_task(self._periodic_flush())

        logger.info("consumer_ready", queue="click_statistics")

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    await self._handle_message(message)

    async def _handle_message(self, message: aio_pika.IncomingMessage) -> None:
        """Parse and buffer a click event message."""
        try:
            data = json.loads(message.body.decode())
            self._buffer.append(data)

            if len(self._buffer) >= BATCH_SIZE:
                await self._flush_buffer()

        except json.JSONDecodeError:
            logger.error("invalid_message_body", body=message.body[:200])
        except Exception:
            logger.exception("message_processing_failed")

    async def _flush_buffer(self) -> None:
        """Write buffered events to PostgreSQL."""
        if not self._buffer:
            return

        events = self._buffer.copy()
        self._buffer.clear()

        try:
            async with async_session_factory() as session:
                click_repo = ClickRepository(session)
                link_repo = LinkRepository(session)

                # Prepare click event records
                click_records = []
                link_updates: dict[str, uuid.UUID] = {}  # short_code -> link_id

                for event in events:
                    link_id = uuid.UUID(event["link_id"])
                    clicked_at = datetime.fromisoformat(event["clicked_at"])

                    click_records.append({
                        "link_id": link_id,
                        "ip_address": event.get("ip_address"),
                        "user_agent": event.get("user_agent"),
                        "referrer": event.get("referrer"),
                        "clicked_at": clicked_at,
                    })

                    link_updates[event["short_code"]] = link_id

                # Batch insert click events
                inserted = await click_repo.bulk_create(click_records)

                # Update click counts (one query per unique link)
                for short_code, link_id in link_updates.items():
                    click_count = sum(
                        1 for e in events if e["short_code"] == short_code
                    )
                    # Use increment_click_count for each event
                    # (simpler than custom batch update)
                    await link_repo.increment_click_count(link_id)

                await session.commit()

                logger.info(
                    "batch_flushed",
                    events=inserted,
                    unique_links=len(link_updates),
                )

        except Exception:
            logger.exception("batch_flush_failed", event_count=len(events))

    async def _periodic_flush(self) -> None:
        """Flush buffer every FLUSH_INTERVAL seconds."""
        while True:
            await asyncio.sleep(FLUSH_INTERVAL)
            if self._buffer:
                await self._flush_buffer()


async def main() -> None:
    consumer = ClickEventConsumer()
    try:
        await consumer.start()
    except KeyboardInterrupt:
        logger.info("consumer_shutting_down")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
