import logging
from typing import Any
from uuid import UUID

from faststream.rabbit import RabbitBroker, RabbitMessage
from sqlalchemy.ext.asyncio import async_sessionmaker

from payment_processor.messaging.broker import (
    RETRY_SCHEDULE_MS,
    RK_DEAD,
    payments_dlx,
    payments_exchange,
    retry_routing_key,
)
from payment_processor.payments.enums import PaymentStatus
from payment_processor.payments.exceptions import PaymentNotFoundError
from payment_processor.payments.gateway import PaymentGateway
from payment_processor.payments.service import PaymentService
from payment_processor.payments.webhook import WebhookClient

logger = logging.getLogger(__name__)

ATTEMPT_HEADER = "x-attempt"


class PaymentConsumer:
    """Обрабатывает события payment.created из очереди payments.new."""

    def __init__(
        self,
        session_factory: async_sessionmaker,
        broker: RabbitBroker,
        webhook_client: WebhookClient,
        gateway: PaymentGateway,
    ) -> None:
        self._session_factory = session_factory
        self._broker = broker
        self._webhook_client = webhook_client
        self._gateway = gateway

    async def handle(self, payload: dict[str, Any], message: RabbitMessage) -> None:
        payment_id = UUID(payload["payment_id"])
        webhook_url = payload["webhook_url"]
        attempt = self._current_attempt(message)

        try:
            payment_status = await self._process_payment(payment_id)
        except PaymentNotFoundError:
            # Нет платежа - ретраить бессмысленно, сразу DLQ
            logger.exception("Payment %s not found in DB, routing to DLQ", payment_id)
            await self._route_to_dlq(payload, message, reason="payment_not_found")
            return
        except Exception:
            logger.exception(
                "Processing payment %s failed (attempt %s)",
                payment_id,
                attempt,
            )
            await self._schedule_retry_or_dlq(
                payload, message, attempt, reason="processing_failed"
            )
            return

        # Webhook - та же retry/DLQ-схема. Повторы безопасны (status != PENDING
        # короткозамыкает _process_payment), клиент должен быть идемпотентен
        try:
            await self._send_webhook(payment_id, webhook_url, payment_status, payload)
        except Exception:
            logger.exception(
                "Webhook for payment %s failed (attempt %s)",
                payment_id,
                attempt,
            )
            await self._schedule_retry_or_dlq(
                payload, message, attempt, reason="webhook_failed"
            )

    def _current_attempt(self, message: RabbitMessage) -> int:
        headers = message.raw_message.headers or {}
        try:
            return int(headers.get(ATTEMPT_HEADER, 0))
        except (TypeError, ValueError):
            return 0

    async def _schedule_retry_or_dlq(
        self,
        payload: dict[str, Any],
        message: RabbitMessage,
        attempt: int,
        reason: str,
    ) -> None:
        if attempt >= len(RETRY_SCHEDULE_MS):
            await self._route_to_dlq(payload, message, reason=reason)
            return

        ttl_ms = RETRY_SCHEDULE_MS[attempt]
        headers = self._forward_headers(message)
        headers[ATTEMPT_HEADER] = attempt + 1

        await self._broker.publish(
            message=payload,
            exchange=payments_exchange,
            routing_key=retry_routing_key(ttl_ms),
            headers=headers,
            persist=True,
        )
        logger.info(
            "Payment %s scheduled for retry #%s in %sms",
            payload.get("payment_id"),
            attempt + 1,
            ttl_ms,
        )

    async def _route_to_dlq(
        self,
        payload: dict[str, Any],
        message: RabbitMessage,
        reason: str,
    ) -> None:
        headers = self._forward_headers(message)
        headers["x-dead-reason"] = reason

        await self._broker.publish(
            message=payload,
            exchange=payments_dlx,
            routing_key=RK_DEAD,
            headers=headers,
            persist=True,
        )
        logger.error(
            "Payment %s routed to DLQ (reason=%s)",
            payload.get("payment_id"),
            reason,
        )

    @staticmethod
    def _forward_headers(message: RabbitMessage) -> dict[str, Any]:
        headers = dict(message.raw_message.headers or {})
        # x-death не нужен - счётчик попыток ведём сами через x-attempt
        headers.pop("x-death", None)
        return headers

    async def _process_payment(self, payment_id: UUID) -> PaymentStatus:
        async with self._session_factory() as session, session.begin():
            current = await PaymentService(session).get_status(payment_id)
        if current != PaymentStatus.PENDING:
            logger.info(
                "Payment %s already in status %s, skipping processing",
                payment_id,
                current,
            )
            return current

        new_status = await self._gateway.charge(payment_id)

        async with self._session_factory() as session, session.begin():
            final_status = await PaymentService(session).mark_processed(
                payment_id,
                new_status,
            )

        logger.info("Payment %s processed with status %s", payment_id, final_status)
        return final_status

    async def _send_webhook(
        self,
        payment_id: UUID,
        webhook_url: str,
        payment_status: PaymentStatus,
        event_payload: dict[str, Any],
    ) -> None:
        webhook_payload = {
            "payment_id": str(payment_id),
            "status": payment_status,
            "amount": event_payload["amount"],
            "currency": event_payload["currency"],
        }

        await self._webhook_client.send(webhook_url, webhook_payload)
