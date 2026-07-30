import json
import logging
import os
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from uuid import UUID

import pika

from api.events.order_events import OrderStatusChangedEvent
from api.models.models import OrderStatus

logger = logging.getLogger(__name__)

ORDER_STATUS_CHANGED_QUEUE = "order.status.changed"
ORDER_STATUS_CHANGED_DLQ = "order.status.changed.dlq"

# Declarado identicamente aqui e em worker.py: os argumentos de uma fila precisam bater em
# toda declaração (RabbitMQ rejeita com 409 PRECONDITION_FAILED se um lado declarar sem
# dead-letter e o outro com), então os dois lados importam esta mesma constante em vez de
# repetir o dict.
QUEUE_ARGUMENTS = {
    "x-dead-letter-exchange": "",
    "x-dead-letter-routing-key": ORDER_STATUS_CHANGED_DLQ,
}


def _json_default(value):
    if isinstance(value, UUID | Decimal | OrderStatus):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value)} is not JSON serializable")


def publish_to_rabbitmq(event: OrderStatusChangedEvent) -> None:
    """Publica o evento na fila RabbitMQ para processamento assíncrono pelo worker
    (ver worker.py). Falha de forma isolada (log + retorno) em vez de propagar: uma
    indisponibilidade do broker não deve derrubar a confirmação/cancelamento do pedido,
    que já foi commitado no banco antes desta chamada (ver order_service.py)."""
    url = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    try:
        connection = pika.BlockingConnection(pika.URLParameters(url))
        try:
            channel = connection.channel()
            channel.queue_declare(queue=ORDER_STATUS_CHANGED_DLQ, durable=True)
            channel.queue_declare(queue=ORDER_STATUS_CHANGED_QUEUE, durable=True, arguments=QUEUE_ARGUMENTS)
            channel.basic_publish(
                exchange="",
                routing_key=ORDER_STATUS_CHANGED_QUEUE,
                body=json.dumps(asdict(event), default=_json_default),
                properties=pika.BasicProperties(content_type="application/json", delivery_mode=2),
            )
        finally:
            connection.close()
    except Exception:
        logger.exception("Failed to publish order_status_changed to RabbitMQ: order_id=%s", event.order_id)
