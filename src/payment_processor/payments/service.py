from sqlalchemy.ext.asyncio import AsyncSession


class PaymentService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_payment(self, idempotency_key, data):
        raise NotImplementedError

    async def get_payment(self, payment_id):
        raise NotImplementedError
