import asyncio
import logging
from contextlib import suppress

from faststream.rabbit import RabbitBroker
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from payment_processor.broker import payments_exchange
from payment_processor.outbox.models import OutboxMessage
from payment_processor.outbox.repository import OutboxRepository

logger = logging.getLogger(__name__)


class OutboxRelay:
    """Читает pending-сообщения из outbox-таблицы и публикует их в брокер.

    Работает в бесконечном цикле с паузой poll_interval между итерациями.
    Безопасен при нескольких параллельных инстансах благодаря
    FOR UPDATE SKIP LOCKED в acquire_batch_for_publishing.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        broker: RabbitBroker,
        poll_interval: float,
        batch_size: int,
    ) -> None:
        self._session_factory = session_factory
        self._broker = broker
        self._poll_interval = poll_interval
        self._batch_size = batch_size
        self._stop_event = asyncio.Event()

    async def run(self) -> None:
        logger.info("Outbox relay started")
        while not self._stop_event.is_set():
            try:
                if await self._process_batch() == 0:
                    await self._sleep_or_stop(self._poll_interval)
            except Exception:
                logger.exception("Unexpected error in relay loop")
                await self._sleep_or_stop(self._poll_interval)
        logger.info("Outbox relay stopped")

    def stop(self) -> None:
        self._stop_event.set()

    async def _process_batch(self) -> int:
        async with self._session_factory() as session, session.begin():
            repo = OutboxRepository(session)
            batch = await repo.acquire_batch_for_publishing(self._batch_size)

            if not batch:
                return 0

            sent_ids: list[int] = []
            for message in batch:
                try:
                    await self._publish(message)
                    sent_ids.append(message.id)
                except Exception as exc:
                    logger.exception(
                        "Failed to publish outbox message id=%s",
                        message.id,
                    )
                    await repo.mark_as_failed(
                        message.id,
                        error=str(exc),
                        attempts=message.attempts + 1,
                    )

            if sent_ids:
                await repo.mark_as_sent(sent_ids)

            logger.info(
                "Processed outbox batch: %s sent, %s failed",
                len(sent_ids),
                len(batch) - len(sent_ids),
            )
            return len(batch)

    async def _publish(self, message: OutboxMessage) -> None:
        await self._broker.publish(
            message=message.payload,
            exchange=payments_exchange,
            routing_key="payments.new",
            headers={
                "event_type": message.event_type,
                "outbox_message_id": str(message.id),
            },
        )

    async def _sleep_or_stop(self, seconds: float) -> None:
        with suppress(TimeoutError):
            await asyncio.wait_for(self._stop_event.wait(), timeout=seconds)
