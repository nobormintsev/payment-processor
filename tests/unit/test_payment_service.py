from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import HttpUrl
from sqlalchemy.exc import IntegrityError

from payment_processor.payments import service as service_module
from payment_processor.payments.enums import Currency, PaymentStatus
from payment_processor.payments.exceptions import (
    IdempotencyConflictError,
    PaymentNotFoundError,
)
from payment_processor.payments.models import Payment
from payment_processor.payments.schemas import CreatePaymentRequest
from payment_processor.payments.service import PaymentService


def _request() -> CreatePaymentRequest:
    return CreatePaymentRequest(
        amount=Decimal("100.00"),
        currency=Currency.RUB,
        description="test",
        metadata={"k": "v"},
        webhook_url=HttpUrl("https://example.com/hook"),
    )


def _existing_payment_from(data: CreatePaymentRequest, key: str) -> Payment:
    return Payment(
        id=uuid4(),
        idempotency_key=key,
        amount=data.amount,
        currency=data.currency,
        description=data.description,
        payment_metadata=data.metadata,
        webhook_url=str(data.webhook_url),
        status=PaymentStatus.PENDING,
    )


@pytest.fixture
def session():
    s = MagicMock()
    s.commit = AsyncMock()
    s.rollback = AsyncMock()
    return s


@pytest.fixture
def payments_repo(monkeypatch):
    repo = MagicMock()
    repo.get_by_idempotency_key = AsyncMock(return_value=None)
    repo.add = MagicMock()
    monkeypatch.setattr(service_module, "PaymentRepository", lambda _session: repo)
    return repo


@pytest.fixture
def outbox_repo(monkeypatch):
    repo = MagicMock()
    repo.add = MagicMock()
    monkeypatch.setattr(service_module, "OutboxRepository", lambda _session: repo)
    return repo


async def test_creates_new_payment_and_outbox_event(
    session,
    payments_repo,
    outbox_repo,
):
    service = PaymentService(session=session)

    payment = await service.create_payment("key-1", _request())

    assert payment.idempotency_key == "key-1"
    assert payment.status == PaymentStatus.PENDING
    payments_repo.add.assert_called_once()
    outbox_repo.add.assert_called_once()
    session.commit.assert_awaited_once()


async def test_returns_existing_payment_on_same_key_same_body(
    session,
    payments_repo,
    outbox_repo,
):
    data = _request()
    existing = _existing_payment_from(data, "key-2")
    payments_repo.get_by_idempotency_key = AsyncMock(return_value=existing)

    service = PaymentService(session=session)
    result = await service.create_payment("key-2", data)

    assert result is existing
    payments_repo.add.assert_not_called()
    outbox_repo.add.assert_not_called()
    session.commit.assert_not_awaited()


async def test_raises_on_same_key_different_body(
    session,
    payments_repo,
    outbox_repo,
):
    data = _request()
    existing = _existing_payment_from(data, "key-3")
    existing.amount = Decimal("999.00")  # другое тело
    payments_repo.get_by_idempotency_key = AsyncMock(return_value=existing)

    service = PaymentService(session=session)

    with pytest.raises(IdempotencyConflictError):
        await service.create_payment("key-3", data)


async def test_returns_existing_on_race_integrity_error(
    session,
    payments_repo,
    outbox_repo,
):
    data = _request()
    existing = _existing_payment_from(data, "key-4")

    # Первый вызов - None (ключа ещё нет). Второй (после IntegrityError) -
    # возвращает уже вставленную параллельным процессом запись.
    payments_repo.get_by_idempotency_key = AsyncMock(side_effect=[None, existing])
    session.commit = AsyncMock(side_effect=IntegrityError("stmt", {}, Exception()))

    service = PaymentService(session=session)
    result = await service.create_payment("key-4", data)

    assert result is existing
    session.rollback.assert_awaited_once()


async def test_get_status_raises_when_missing(session, payments_repo, outbox_repo):
    payments_repo.get_by_id = AsyncMock(return_value=None)
    service = PaymentService(session=session)
    with pytest.raises(PaymentNotFoundError):
        await service.get_status(uuid4())


async def test_mark_processed_sets_status_when_pending(
    session,
    payments_repo,
    outbox_repo,
):
    payment = _existing_payment_from(_request(), "key-mp1")
    payments_repo.get_by_id = AsyncMock(return_value=payment)

    service = PaymentService(session=session)
    result = await service.mark_processed(payment.id, PaymentStatus.SUCCEEDED)

    assert result is PaymentStatus.SUCCEEDED
    assert payment.status is PaymentStatus.SUCCEEDED
    assert payment.processed_at is not None


async def test_mark_processed_is_idempotent_when_not_pending(
    session,
    payments_repo,
    outbox_repo,
):
    payment = _existing_payment_from(_request(), "key-mp2")
    payment.status = PaymentStatus.SUCCEEDED
    payments_repo.get_by_id = AsyncMock(return_value=payment)

    service = PaymentService(session=session)
    result = await service.mark_processed(payment.id, PaymentStatus.FAILED)

    assert result is PaymentStatus.SUCCEEDED  # не перезаписано
    assert payment.status is PaymentStatus.SUCCEEDED
