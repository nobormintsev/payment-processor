import asyncio
import logging
import signal

from payment_processor.broker import broker
from payment_processor.core.config import settings
from payment_processor.core.logging import configure_logging
from payment_processor.database.session import engine, session_factory
from payment_processor.outbox.relay import OutboxRelay

logger = logging.getLogger(__name__)


async def main() -> None:
    configure_logging(settings.log_level, settings.log_json)
    logger.info("Starting relay process")

    await broker.connect()
    logger.info("Connected to broker")

    relay = OutboxRelay(
        session_factory=session_factory,
        broker=broker,
        poll_interval=settings.outbox.poll_interval_seconds,
        batch_size=settings.outbox.batch_size,
    )

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, relay.stop)

    try:
        await relay.run()
    finally:
        logger.info("Shutting down relay process")
        await broker.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
