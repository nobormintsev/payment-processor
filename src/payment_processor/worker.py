import asyncio
import logging
import signal

from payment_processor.core.config import settings
from payment_processor.core.logging import configure_logging
from payment_processor.database.session import engine, session_factory
from payment_processor.messaging.broker import (
    broker,
    declare_topology,
    payments_exchange,
    payments_new_queue,
)
from payment_processor.payments.consumer import PaymentConsumer
from payment_processor.payments.gateway import FakePaymentGateway
from payment_processor.payments.webhook import WebhookClient

logger = logging.getLogger(__name__)


async def main() -> None:
    configure_logging(settings.log_level, settings.log_json)
    logger.info("Starting worker process")

    webhook_client = WebhookClient(
        timeout=settings.payments.webhook_timeout_seconds,
        max_retries=settings.payments.webhook_max_retries,
    )
    webhook_client.start()

    gateway = FakePaymentGateway(
        min_seconds=settings.payments.processing_min_seconds,
        max_seconds=settings.payments.processing_max_seconds,
        success_rate=settings.payments.success_rate,
    )

    consumer = PaymentConsumer(
        session_factory=session_factory,
        broker=broker,
        webhook_client=webhook_client,
        gateway=gateway,
    )

    broker.subscriber(payments_new_queue, exchange=payments_exchange)(consumer.handle)

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop_event.set)

    try:
        await broker.connect()
        await declare_topology(broker)
        await broker.start()
        logger.info("Worker is listening on payments.new")
        await stop_event.wait()
    finally:
        logger.info("Shutting down worker process")
        await broker.stop()
        await webhook_client.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
