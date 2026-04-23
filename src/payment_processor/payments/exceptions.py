from uuid import UUID

from payment_processor.core.exceptions import ConflictError, NotFoundError


class PaymentNotFoundError(NotFoundError):
    def __init__(self, payment_id: UUID) -> None:
        super().__init__(f"Payment {payment_id} not found")
        self.payment_id = payment_id


class IdempotencyConflictError(ConflictError):
    def __init__(self, idempotency_key: str) -> None:
        super().__init__(
            f"Idempotency key '{idempotency_key}' conflicts with existing request",
        )
        self.idempotency_key = idempotency_key


class WebhookError(Exception):
    pass


class RetriableWebhookError(WebhookError):
    pass


class PermanentWebhookError(WebhookError):
    pass
