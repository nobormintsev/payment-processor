from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from payment_processor.core.time import utcnow
from payment_processor.outbox.models import OutboxMessage
from payment_processor.outbox.repository import OutboxRepository
from payment_processor.payments.enums import PaymentStatus
from payment_processor.payments.events import PaymentCreatedV1
from payment_processor.payments.exceptions import (
    IdempotencyConflictError,
    PaymentNotFoundError,
)
from payment_processor.payments.models import Payment
from payment_processor.payments.repository import PaymentRepository
from payment_processor.payments.schemas import CreatePaymentRequest


class PaymentService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._payments = PaymentRepository(session)
        self._outbox = OutboxRepository(session)

    async def create_payment(
        self,
        idempotency_key: str,
        data: CreatePaymentRequest,
    ) -> Payment:
        # Ключ уже использовался - возвращаем существующий платёж
        existing = await self._payments.get_by_idempotency_key(idempotency_key)
        if existing is not None:
            if not self._matches_request(existing, data):
                raise IdempotencyConflictError(idempotency_key)
            return existing

        # Платёж и событие outbox одной транзакцией
        payment = Payment(
            id=uuid4(),
            idempotency_key=idempotency_key,
            amount=data.amount,
            currency=data.currency,
            description=data.description,
            payment_metadata=data.metadata,
            webhook_url=str(data.webhook_url),
            status=PaymentStatus.PENDING,
        )
        self._payments.add(payment)

        event = PaymentCreatedV1(
            occurred_at=utcnow(),
            payment_id=payment.id,
            amount=payment.amount,
            currency=payment.currency,
            webhook_url=str(payment.webhook_url),
        )
        self._outbox.add(
            OutboxMessage(
                event_type=event.event_type,
                payload=event.model_dump(mode="json"),
            )
        )

        try:
            await self._session.commit()
        except IntegrityError as err:
            # Race - полагается на UNIQUE(idempotency_key); другие unique-индексы сломают ветку
            await self._session.rollback()
            existing = await self._payments.get_by_idempotency_key(idempotency_key)
            if existing is None:
                raise
            if not self._matches_request(existing, data):
                raise IdempotencyConflictError(idempotency_key) from err
            return existing

        return payment

    async def get_payment(self, payment_id: UUID) -> Payment:
        payment = await self._payments.get_by_id(payment_id)
        if payment is None:
            raise PaymentNotFoundError(payment_id)

        return payment

    async def get_status(self, payment_id: UUID) -> PaymentStatus:
        payment = await self.get_payment(payment_id)
        return payment.status

    async def mark_processed(
        self, payment_id: UUID, status: PaymentStatus
    ) -> PaymentStatus:
        """Переводит PENDING -> status. Если платёж уже обработан - возвращает
        его текущий статус без изменений. Транзакцией управляет вызывающий.
        """
        payment = await self._payments.get_by_id(payment_id)
        if payment is None:
            raise PaymentNotFoundError(payment_id)
        if payment.status != PaymentStatus.PENDING:
            return payment.status

        payment.status = status
        payment.processed_at = utcnow()
        return status

    @staticmethod
    def _matches_request(payment: Payment, data: CreatePaymentRequest) -> bool:
        """Проверяет, что повторный запрос с тем же idempotency-key имеет то же тело."""
        return (
            payment.amount == data.amount
            and payment.currency == data.currency
            and payment.description == data.description
            and payment.payment_metadata == data.metadata
            and payment.webhook_url == str(data.webhook_url)
        )
