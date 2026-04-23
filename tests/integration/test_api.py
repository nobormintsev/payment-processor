from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from payment_processor.core.config import settings
from payment_processor.main import app
from payment_processor.payments.deps import get_payment_service
from payment_processor.payments.enums import Currency, PaymentStatus
from payment_processor.payments.exceptions import (
    IdempotencyConflictError,
    PaymentNotFoundError,
)
from payment_processor.payments.models import Payment

API_KEY = settings.api_key.get_secret_value()

PAYLOAD = {
    "amount": "199.99",
    "currency": "RUB",
    "description": "test",
    "metadata": {"order": "42"},
    "webhook_url": "https://example.com/hook",
}


def _payment(
    payment_id: UUID | None = None,
    status: PaymentStatus = PaymentStatus.PENDING,
) -> Payment:
    return Payment(
        id=payment_id or uuid4(),
        idempotency_key="some-key",
        amount=Decimal("199.99"),
        currency=Currency.RUB,
        description="test",
        payment_metadata={"order": "42"},
        webhook_url="https://example.com/hook",
        status=status,
        created_at=datetime.now(UTC),
        processed_at=None,
    )


@pytest.fixture
def service():
    return AsyncMock()


@pytest.fixture
async def client(service) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_payment_service] = lambda: service
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def test_create_payment_requires_api_key(client):
    response = await client.post(
        "/api/v1/payments",
        headers={"Idempotency-Key": "k1"},
        json=PAYLOAD,
    )
    assert response.status_code == 401


async def test_create_payment_returns_202(client, service):
    service.create_payment.return_value = _payment()

    response = await client.post(
        "/api/v1/payments",
        headers={"X-API-Key": API_KEY, "Idempotency-Key": "k1"},
        json=PAYLOAD,
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert "payment_id" in body
    assert "created_at" in body


async def test_create_payment_conflict_on_idempotency_mismatch(client, service):
    service.create_payment.side_effect = IdempotencyConflictError("k1")

    response = await client.post(
        "/api/v1/payments",
        headers={"X-API-Key": API_KEY, "Idempotency-Key": "k1"},
        json=PAYLOAD,
    )
    assert response.status_code == 409


async def test_create_payment_rejects_invalid_body(client):
    bad_payload = {**PAYLOAD, "amount": "-1.00"}
    response = await client.post(
        "/api/v1/payments",
        headers={"X-API-Key": API_KEY, "Idempotency-Key": "k1"},
        json=bad_payload,
    )
    assert response.status_code == 422


async def test_get_payment_not_found(client, service):
    missing_id = uuid4()
    service.get_payment.side_effect = PaymentNotFoundError(missing_id)

    response = await client.get(
        f"/api/v1/payments/{missing_id}",
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 404


async def test_get_payment_returns_details(client, service):
    payment = _payment(status=PaymentStatus.SUCCEEDED)
    service.get_payment.return_value = payment

    response = await client.get(
        f"/api/v1/payments/{payment.id}",
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(payment.id)
    assert body["status"] == "succeeded"
    assert body["metadata"] == {"order": "42"}
