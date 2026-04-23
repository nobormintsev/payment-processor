from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from payment_processor.messaging.broker import (
    RETRY_SCHEDULE_MS,
    RK_DEAD,
    payments_dlx,
    payments_exchange,
    retry_routing_key,
)
from payment_processor.payments.consumer import ATTEMPT_HEADER, PaymentConsumer
from payment_processor.payments.enums import PaymentStatus
from payment_processor.payments.exceptions import PaymentNotFoundError


def _message(headers: dict[str, Any] | None = None) -> MagicMock:
    msg = MagicMock()
    msg.raw_message.headers = headers or {}
    return msg


def _make_consumer(**overrides: Any) -> tuple[PaymentConsumer, MagicMock, MagicMock]:
    broker = MagicMock()
    broker.publish = AsyncMock()
    webhook_client = MagicMock()
    webhook_client.send = AsyncMock()
    gateway = MagicMock()
    gateway.charge = AsyncMock(return_value=PaymentStatus.SUCCEEDED)

    consumer = PaymentConsumer(
        session_factory=MagicMock(),
        broker=broker,
        webhook_client=webhook_client,
        gateway=gateway,
    )
    for attr, value in overrides.items():
        setattr(consumer, attr, value)
    return consumer, broker, webhook_client


def _payload(payment_id=None) -> dict[str, Any]:
    return {
        "payment_id": str(payment_id or uuid4()),
        "webhook_url": "https://example.com/hook",
        "amount": "10.00",
        "currency": "RUB",
    }


async def test_happy_path_acks_and_sends_webhook(monkeypatch):
    consumer, broker, webhook_client = _make_consumer()
    monkeypatch.setattr(
        consumer,
        "_process_payment",
        AsyncMock(return_value=PaymentStatus.SUCCEEDED),
    )

    await consumer.handle(_payload(), _message())

    broker.publish.assert_not_awaited()  # no retry / no DLQ
    webhook_client.send.assert_awaited_once()


async def test_payment_not_found_routes_straight_to_dlq(monkeypatch):
    consumer, broker, _ = _make_consumer()
    monkeypatch.setattr(
        consumer,
        "_process_payment",
        AsyncMock(side_effect=PaymentNotFoundError(uuid4())),
    )

    await consumer.handle(_payload(), _message())

    broker.publish.assert_awaited_once()
    kwargs = broker.publish.await_args.kwargs
    assert kwargs["exchange"] is payments_dlx
    assert kwargs["routing_key"] == RK_DEAD
    assert kwargs["headers"]["x-dead-reason"] == "payment_not_found"


async def test_first_failure_schedules_retry_with_incremented_attempt(monkeypatch):
    consumer, broker, _ = _make_consumer()
    monkeypatch.setattr(
        consumer,
        "_process_payment",
        AsyncMock(side_effect=RuntimeError("boom")),
    )

    await consumer.handle(_payload(), _message())  # attempt 0

    broker.publish.assert_awaited_once()
    kwargs = broker.publish.await_args.kwargs
    assert kwargs["exchange"] is payments_exchange
    assert kwargs["routing_key"] == retry_routing_key(RETRY_SCHEDULE_MS[0])
    assert kwargs["headers"][ATTEMPT_HEADER] == 1


async def test_exhausted_retries_go_to_dlq(monkeypatch):
    consumer, broker, _ = _make_consumer()
    monkeypatch.setattr(
        consumer,
        "_process_payment",
        AsyncMock(side_effect=RuntimeError("still failing")),
    )

    max_attempts = len(RETRY_SCHEDULE_MS)
    await consumer.handle(
        _payload(),
        _message(headers={ATTEMPT_HEADER: max_attempts}),
    )

    broker.publish.assert_awaited_once()
    kwargs = broker.publish.await_args.kwargs
    assert kwargs["exchange"] is payments_dlx
    assert kwargs["routing_key"] == RK_DEAD
    assert kwargs["headers"]["x-dead-reason"] == "processing_failed"


async def test_webhook_failure_schedules_retry(monkeypatch):
    consumer, broker, webhook_client = _make_consumer()
    monkeypatch.setattr(
        consumer,
        "_process_payment",
        AsyncMock(return_value=PaymentStatus.SUCCEEDED),
    )
    webhook_client.send.side_effect = RuntimeError("webhook down")

    await consumer.handle(_payload(), _message())  # attempt 0

    webhook_client.send.assert_awaited_once()
    broker.publish.assert_awaited_once()
    kwargs = broker.publish.await_args.kwargs
    assert kwargs["exchange"] is payments_exchange
    assert kwargs["routing_key"] == retry_routing_key(RETRY_SCHEDULE_MS[0])
    assert kwargs["headers"][ATTEMPT_HEADER] == 1


async def test_webhook_failure_after_max_attempts_goes_to_dlq(monkeypatch):
    consumer, broker, webhook_client = _make_consumer()
    monkeypatch.setattr(
        consumer,
        "_process_payment",
        AsyncMock(return_value=PaymentStatus.SUCCEEDED),
    )
    webhook_client.send.side_effect = RuntimeError("still down")

    max_attempts = len(RETRY_SCHEDULE_MS)
    await consumer.handle(
        _payload(),
        _message(headers={ATTEMPT_HEADER: max_attempts}),
    )

    broker.publish.assert_awaited_once()
    kwargs = broker.publish.await_args.kwargs
    assert kwargs["exchange"] is payments_dlx
    assert kwargs["routing_key"] == RK_DEAD
    assert kwargs["headers"]["x-dead-reason"] == "webhook_failed"


async def test_forward_headers_drops_x_death():
    consumer, _, _ = _make_consumer()
    headers = consumer._forward_headers(
        _message(headers={"x-death": [{"count": 7}], ATTEMPT_HEADER: 1}),
    )
    assert "x-death" not in headers
    assert headers[ATTEMPT_HEADER] == 1


@pytest.mark.parametrize(
    "raw_value, expected", [(None, 0), ("abc", 0), ("3", 3), (2, 2)]
)
def test_current_attempt_parses_safely(raw_value, expected):
    consumer, _, _ = _make_consumer()
    headers = {} if raw_value is None else {ATTEMPT_HEADER: raw_value}
    assert consumer._current_attempt(_message(headers=headers)) == expected
