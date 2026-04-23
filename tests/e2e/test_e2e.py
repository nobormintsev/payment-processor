"""End-to-end тест поверх живой docker compose-среды.

Требует, чтобы compose был поднят:
    docker compose up -d --build

Запуск:
    poetry run pytest -m e2e

Прогоняет полный флоу: POST /payments -> брокер -> worker эмулирует обработку
-> статус в БД меняется. Webhook не проверяется (требует reverse-туннеля
до хоста); для ручной проверки используйте https://webhook.site.
"""

import asyncio
import os
import uuid
from decimal import Decimal

import httpx
import pytest

pytestmark = pytest.mark.e2e

API_URL = os.environ.get("E2E_API_URL", "http://localhost:8000")
API_KEY = os.environ.get("API_KEY", "local-dev-secret-change-me")
POLL_TIMEOUT_SECONDS = 30.0
POLL_INTERVAL_SECONDS = 0.5


async def _wait_for_terminal_status(client: httpx.AsyncClient, payment_id: str) -> dict:
    deadline = asyncio.get_event_loop().time() + POLL_TIMEOUT_SECONDS
    while asyncio.get_event_loop().time() < deadline:
        response = await client.get(
            f"/api/v1/payments/{payment_id}",
            headers={"X-API-Key": API_KEY},
        )
        response.raise_for_status()
        body = response.json()
        if body["status"] != "pending":
            return body
        await asyncio.sleep(POLL_INTERVAL_SECONDS)

    raise AssertionError(f"Payment {payment_id} stuck in pending")


async def test_full_payment_flow():
    idempotency_key = f"e2e-{uuid.uuid4()}"
    payload = {
        "amount": "42.00",
        "currency": "RUB",
        "description": "e2e test",
        "metadata": {"run": idempotency_key},
        "webhook_url": "https://example.invalid/hook",
    }

    async with httpx.AsyncClient(base_url=API_URL, timeout=10.0) as client:
        create_resp = await client.post(
            "/api/v1/payments",
            headers={"X-API-Key": API_KEY, "Idempotency-Key": idempotency_key},
            json=payload,
        )
        assert create_resp.status_code == 202
        created = create_resp.json()
        payment_id = created["payment_id"]
        assert created["status"] == "pending"

        # Повторный вызов с тем же ключом → тот же payment_id
        replay_resp = await client.post(
            "/api/v1/payments",
            headers={"X-API-Key": API_KEY, "Idempotency-Key": idempotency_key},
            json=payload,
        )
        assert replay_resp.status_code == 202
        assert replay_resp.json()["payment_id"] == payment_id

        # Ждём, пока worker обработает платёж
        final = await _wait_for_terminal_status(client, payment_id)

        assert final["status"] in {"succeeded", "failed"}
        assert final["processed_at"] is not None
        assert Decimal(final["amount"]) == Decimal("42.00")
