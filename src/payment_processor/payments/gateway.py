import asyncio
import logging
import random
from typing import Protocol
from uuid import UUID

from payment_processor.payments.enums import PaymentStatus

logger = logging.getLogger(__name__)


class PaymentGateway(Protocol):
    """Внешний платёжный шлюз. Возвращает итоговый статус платежа."""

    async def charge(self, payment_id: UUID) -> PaymentStatus: ...


class FakePaymentGateway:
    """Эмуляция платёжного шлюза: задержка + вероятностный исход."""

    def __init__(
        self,
        min_seconds: float,
        max_seconds: float,
        success_rate: float,
    ) -> None:
        self._min = min_seconds
        self._max = max_seconds
        self._success_rate = success_rate

    async def charge(self, payment_id: UUID) -> PaymentStatus:
        delay = random.uniform(self._min, self._max)  # noqa: S311
        await asyncio.sleep(delay)

        succeeded = random.random() < self._success_rate  # noqa: S311
        status = PaymentStatus.SUCCEEDED if succeeded else PaymentStatus.FAILED
        logger.info("Gateway processed payment %s: %s", payment_id, status)
        return status
