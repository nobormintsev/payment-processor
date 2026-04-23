# payment-processor

Асинхронный сервис обработки платежей: принимает запрос по REST, публикует событие в RabbitMQ, эмулирует платёжный шлюз и уведомляет клиента webhook'ом.

## Стек

Python 3.13, FastAPI, SQLAlchemy 2.0 (async), Pydantic v2, PostgreSQL, RabbitMQ (FastStream), Alembic, Docker.

## Как это работает

1. Клиент шлёт `POST /api/v1/payments` с заголовком `Idempotency-Key`;
2. **api** сохраняет платёж и событие в одной транзакции (outbox pattern), отвечает `202 Accepted`;
3. **relay** вычитывает outbox и публикует событие в RabbitMQ;
4. **worker** обрабатывает платёж (эмуляция 2-5с, 90% успех), обновляет статус, шлёт webhook;
5. При любой ошибке (обработка или webhook) - повтор через TTL-очереди (1s / 5s / 25s), после 3 попыток в DLQ.

## Быстрый старт

```bash
cp .env.example .env
docker compose up -d --build
```

Поднимутся `postgres`, `rabbitmq`, `migrator` (одноразовая миграция), `api` (:8000), `worker`, `relay`.
RabbitMQ UI: <http://localhost:15672>.

Проверка:

```bash
curl http://localhost:8000/database/health
```

## Примеры

### Создать платёж

```bash
curl -X POST http://localhost:8000/api/v1/payments \
  -H "X-API-Key: local-dev-secret-change-me" \
  -H "Idempotency-Key: order-42" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": "199.99",
    "currency": "RUB",
    "description": "Premium subscription",
    "metadata": {"order_id": "42"},
    "webhook_url": "https://webhook.site/<your-uuid>"
  }'
```

Ответ:

```json
{
  "payment_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "created_at": "2026-04-23T12:00:00Z"
}
```

### Получить платёж

```bash
curl http://localhost:8000/api/v1/payments/<payment_id> \
  -H "X-API-Key: local-dev-secret-change-me"
```

Ответ:

```json
{
  "id": "e0254f04-c2d8-45a1-8337-c7c887205bde",
  "amount": "1.00",
  "currency": "RUB",
  "description": "string",
  "metadata": {
    "additionalProp1": {}
  },
  "status": "succeeded",
  "webhook_url": "https://webhook.site/e260d3d6-b745-4436-b639-445a878635bd",
  "created_at": "2026-04-23T09:59:11.638329Z",
  "processed_at": "2026-04-23T09:59:14.420792Z"
}
```

### Что приходит в webhook:

```json
{
  "payment_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "succeeded",
  "amount": "199.99",
  "currency": "RUB"
}
```

Webhook должен быть идемпотентным: при ретраях одно и то же событие может прийти несколько раз.

## Идемпотентность

`Idempotency-Key` обязателен. Повторный запрос с тем же ключом и телом вернёт тот же `payment_id`. Разные тела при одном ключе - `409 Conflict`.

## Конфигурация

Описана в [`.env.example`](.env.example). Обязательные переменные окружения: `API_KEY`, `POSTGRES_*`, `RABBITMQ_*`.

## Локальный запуск без Docker

```bash
docker compose up -d postgres rabbitmq
poetry install --with dev
poetry run alembic upgrade head

poetry run uvicorn payment_processor.main:app --reload
poetry run python -m payment_processor.worker
poetry run python -m payment_processor.relay
```

## Тесты

```bash
poetry run pytest  # unit + integration
poetry run pytest -m e2e  # e2e, требует поднятого docker compose
```

## Разработка

```bash
poetry run ruff check src/ tests/
poetry run ruff format src/ tests/
poetry run pre-commit install

# Новая миграция
poetry run alembic revision --autogenerate -m "..."
poetry run alembic upgrade head
```
