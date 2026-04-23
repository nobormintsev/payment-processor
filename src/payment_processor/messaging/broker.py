from faststream.rabbit import ExchangeType, RabbitBroker, RabbitExchange, RabbitQueue

from payment_processor.core.config import settings

# Routing keys
RK_NEW = "payments.new"
RK_DEAD = "payments.dead"

# TTL retry-очередей - экспоненциальный backoff, длина = лимит попыток до DLQ
RETRY_SCHEDULE_MS: tuple[int, ...] = tuple(settings.payments.retry_schedule_ms)


def retry_routing_key(ttl_ms: int) -> str:
    return f"payments.retry.{ttl_ms}ms"


# Основной exchange - новые события и возврат из retry-очередей
payments_exchange = RabbitExchange(
    name="payments",
    type=ExchangeType.DIRECT,
    durable=True,
)

# DLX - сюда consumer явно публикует окончательно упавшие сообщения
payments_dlx = RabbitExchange(
    name="payments.dlx",
    type=ExchangeType.DIRECT,
    durable=True,
)

# Очередь новых платежей - retry делает сам consumer (счётчик x-attempt в приложении)
payments_new_queue = RabbitQueue(
    name="payments.new",
    durable=True,
    routing_key=RK_NEW,
)

# Retry-очереди - по истечении TTL dead-letter возвращает сообщение в payments.new
payments_retry_queues: tuple[RabbitQueue, ...] = tuple(
    RabbitQueue(
        name=f"payments.retry.{ttl}ms",
        durable=True,
        routing_key=retry_routing_key(ttl),
        arguments={
            "x-message-ttl": ttl,
            "x-dead-letter-exchange": payments_exchange.name,
            "x-dead-letter-routing-key": RK_NEW,
        },
    )
    for ttl in RETRY_SCHEDULE_MS
)

# DLQ - окончательно упавшие сообщения
payments_dlq = RabbitQueue(
    name="payments.dlq",
    durable=True,
    routing_key=RK_DEAD,
)

broker = RabbitBroker(settings.rabbit.url)


async def declare_topology(broker: RabbitBroker) -> None:
    """Создаёт exchanges/queues/bindings.

    Идемпотентна - безопасно вызывать на каждом старте.
    """
    main_exch = await broker.declare_exchange(payments_exchange)
    dlx_exch = await broker.declare_exchange(payments_dlx)

    new_q = await broker.declare_queue(payments_new_queue)
    await new_q.bind(main_exch, routing_key=RK_NEW)

    for retry_q_def in payments_retry_queues:
        retry_q = await broker.declare_queue(retry_q_def)
        await retry_q.bind(main_exch, routing_key=retry_q_def.routing_key)

    dlq = await broker.declare_queue(payments_dlq)
    await dlq.bind(dlx_exch, routing_key=RK_DEAD)
