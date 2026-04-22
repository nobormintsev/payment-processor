from faststream.rabbit import ExchangeType, RabbitBroker, RabbitExchange, RabbitQueue

from payment_processor.core.config import settings

# Основной exchange для событий платежей
payments_exchange = RabbitExchange(
    name="payments",
    type=ExchangeType.DIRECT,
    durable=True,
)

# Dead-letter exchange: сюда уходят сообщения, которые не удалось обработать
payments_dlx = RabbitExchange(
    name="payments.dlx",
    type=ExchangeType.DIRECT,
    durable=True,
)

# Основная очередь для новых платежей
payments_new_queue = RabbitQueue(
    name="payments.new",
    durable=True,
    arguments={
        # При reject/nack без requeue сообщение уйдёт в DLX
        "x-dead-letter-exchange": "payments.dlx",
        "x-dead-letter-routing-key": "payments.new",
    },
    routing_key="payments.new",
)

# DLQ, куда уходят окончательно упавшие сообщения
payments_dlq = RabbitQueue(
    name="payments.dlq",
    durable=True,
    routing_key="payments.new",
)

broker = RabbitBroker(settings.rabbit.url)
