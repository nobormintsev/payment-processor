from collections.abc import Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from payment_processor.core.time import utcnow
from payment_processor.outbox.enums import OutboxStatus
from payment_processor.outbox.models import OutboxMessage


class OutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, message: OutboxMessage) -> None:
        self._session.add(message)

    async def acquire_batch_for_publishing(
        self, batch_size: int
    ) -> Sequence[OutboxMessage]:
        stmt = (
            select(OutboxMessage)
            .where(OutboxMessage.status == OutboxStatus.PENDING)
            .order_by(OutboxMessage.created_at)
            .limit(batch_size)
            # Поддержка нескольких relay: пропускает записи, заблокированные другими
            # транзакциями
            .with_for_update(skip_locked=True)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def mark_as_sent(self, message_ids: Sequence[int]) -> None:
        if not message_ids:
            return

        stmt = (
            update(OutboxMessage)
            .where(OutboxMessage.id.in_(message_ids))
            .values(status=OutboxStatus.SENT, sent_at=utcnow())
        )
        await self._session.execute(stmt)

    async def mark_as_failed(self, message_id: int, error: str, attempts: int) -> None:
        stmt = (
            update(OutboxMessage)
            .where(OutboxMessage.id == message_id)
            .values(
                status=OutboxStatus.FAILED,
                last_error=error,
                attempts=attempts,
            )
        )
        await self._session.execute(stmt)
