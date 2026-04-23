from uuid import uuid4

import pytest

from payment_processor.payments.enums import PaymentStatus
from payment_processor.payments.gateway import FakePaymentGateway


@pytest.mark.parametrize(
    "success_rate, expected",
    [(1.0, PaymentStatus.SUCCEEDED), (0.0, PaymentStatus.FAILED)],
)
async def test_fake_gateway_deterministic_endpoints(success_rate, expected):
    gateway = FakePaymentGateway(
        min_seconds=0.0, max_seconds=0.0, success_rate=success_rate
    )
    assert await gateway.charge(uuid4()) is expected
