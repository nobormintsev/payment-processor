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
        # Если ключ уже использовался, возвращаем существующий платёж
        existing = await self._payments.get_by_idempotency_key(idempotency_key)
        if existing is not None:
            if not self._matches_request(existing, data):
                raise IdempotencyConflictError(idempotency_key)
            return existing

        # Создаём платёж и событие в одной транзакции
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
            # Race condition: между get_by_idempotency_key и commit кто-то
            # успел вставить платёж с тем же ключом
            await self._session.rollback()
            existing = await self._payments.get_by_idempotency_key(idempotency_key)
            if existing is None:
                raise
            if not self._matches_request(existing, data):
                raise IdempotencyConflictError(idempotency_key) from err
            return existing

        await self._session.refresh(payment)
        return payment

    async def get_payment(self, payment_id: UUID) -> Payment:
        payment = await self._payments.get_by_id(payment_id)
        if payment is None:
            raise PaymentNotFoundError(payment_id)
        return payment

    @staticmethod
    def _matches_request(payment: Payment, data: CreatePaymentRequest) -> bool:
        """
        Проверка, что повторный запрос с тем же idempotency-key имеет то же тело.
        """
        return (
            payment.amount == data.amount
            and payment.currency == data.currency
            and payment.description == data.description
            and payment.payment_metadata == data.metadata
            and payment.webhook_url == str(data.webhook_url)
        )
