import json
from datetime import datetime, timezone
from typing import Any

import aio_pika
import structlog

from app.config import settings

logger = structlog.get_logger()


class RabbitMQManager:
    """Manages RabbitMQ connection and provides publishing methods."""

    EXCHANGE_NAME = "link_events"
    CLICK_QUEUE = "click_statistics"
    CLICK_ROUTING_KEY = "link.clicked"

    def __init__(self) -> None:
        self._connection: aio_pika.abc.AbstractRobustConnection | None = None
        self._channel: aio_pika.abc.AbstractChannel | None = None
        self._exchange: aio_pika.abc.AbstractExchange | None = None

    async def connect(self) -> None:
        """Establish connection, declare exchange and queue."""
        self._connection = await aio_pika.connect_robust(settings.rabbitmq_url)
        self._channel = await self._connection.channel()

        self._exchange = await self._channel.declare_exchange(
            self.EXCHANGE_NAME,
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )

        queue = await self._channel.declare_queue(
            self.CLICK_QUEUE,
            durable=True,
        )
        await queue.bind(self._exchange, routing_key=self.CLICK_ROUTING_KEY)

        logger.info("rabbitmq_connected", url=settings.rabbitmq_url)

    async def disconnect(self) -> None:
        """Close RabbitMQ connection gracefully."""
        if self._connection:
            await self._connection.close()
        logger.info("rabbitmq_disconnected")

    async def publish_click_event(
        self,
        link_id: str,
        short_code: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
        referrer: str | None = None,
    ) -> None:
        """Publish a click event to the click_statistics queue.

        This is fire-and-forget — errors are logged but don't
        break the redirect flow.
        """
        if self._exchange is None:
            logger.warning("rabbitmq_not_connected", action="publish_click_event")
            return

        body: dict[str, Any] = {
            "link_id": link_id,
            "short_code": short_code,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "referrer": referrer,
            "clicked_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            message = aio_pika.Message(
                body=json.dumps(body).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                content_type="application/json",
            )
            await self._exchange.publish(
                message,
                routing_key=self.CLICK_ROUTING_KEY,
            )
            logger.debug("click_event_published", short_code=short_code)
        except Exception:
            logger.exception("click_event_publish_failed", short_code=short_code)


rabbitmq_manager = RabbitMQManager()
