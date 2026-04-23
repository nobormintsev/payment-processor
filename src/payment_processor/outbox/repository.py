from collections.abc import Sequence

from sqlalchemy import and_, select, update
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
        self,
        batch_size: int,
        max_attempts: int,
    ) -> Sequence[OutboxMessage]:
        stmt = (
            select(OutboxMessage)
            .where(
                and_(
                    OutboxMessage.status == OutboxStatus.PENDING,
                    OutboxMessage.attempts < max_attempts,
                )
            )
            .order_by(OutboxMessage.created_at)
            .limit(batch_size)
            # SKIP LOCKED - безопасно при нескольких параллельных relay
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

    async def record_publish_failure(
        self,
        message_id: int,
        error: str,
        attempts: int,
        max_attempts: int,
    ) -> None:
        """Фиксирует неуспешную попытку публикации.

        Переводит сообщение в FAILED только когда исчерпан max_attempts - иначе
        оставляет PENDING, чтобы релей попробовал снова на следующей итерации.
        """
        new_status = (
            OutboxStatus.FAILED if attempts >= max_attempts else OutboxStatus.PENDING
        )
        stmt = (
            update(OutboxMessage)
            .where(OutboxMessage.id == message_id)
            .values(
                status=new_status,
                last_error=error,
                attempts=attempts,
            )
        )
        await self._session.execute(stmt)
