import logging
from http import HTTPStatus
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    before_sleep_log,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from payment_processor.payments.exceptions import (
    PermanentWebhookError,
    RetriableWebhookError,
)

logger = logging.getLogger(__name__)


class WebhookClient:
    """Отправляет webhook-уведомления клиенту, сделавшему платеж.

    Управляет общим httpx.AsyncClient с connection pool.
    start()/close() вызываются в lifespan воркера.
    """

    def __init__(self, timeout: float, max_retries: int) -> None:
        self._timeout = timeout
        self._max_retries = max_retries
        self._client: httpx.AsyncClient | None = None

    def start(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def send(self, url: str, payload: dict[str, Any]) -> None:
        if self._client is None:
            raise RuntimeError("WebhookClient is not initialized. Call start() first.")

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(RetriableWebhookError),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        ):
            with attempt:
                await self._send_once(url, payload)

    async def _send_once(self, url: str, payload: dict[str, Any]) -> None:
        try:
            response = await self._client.post(url, json=payload)
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            raise RetriableWebhookError(f"Network error: {exc}") from exc

        status_code = response.status_code
        body_preview = response.text[:200]

        if (
            status_code >= HTTPStatus.INTERNAL_SERVER_ERROR
            or status_code == HTTPStatus.TOO_MANY_REQUESTS
        ):
            raise RetriableWebhookError(
                f"Retriable status {status_code}: {body_preview}"
            )

        if status_code >= HTTPStatus.BAD_REQUEST:
            raise PermanentWebhookError(
                f"Client rejected webhook: {status_code} {body_preview}"
            )

        logger.info("Webhook delivered to %s with status %s", url, status_code)
