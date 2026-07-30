import json
import logging
import os
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pika

from api.events.order_status_email import build_order_status_email_html
from api.events.rabbitmq_publisher import (
    ORDER_STATUS_CHANGED_DLQ,
    ORDER_STATUS_CHANGED_QUEUE,
    QUEUE_ARGUMENTS,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("worker")

RECONNECT_DELAY_SECONDS = 5
RETRY_BACKOFF_SECONDS = 2
MAX_RETRIES = 3

_REQUIRED_EVENT_FIELDS = (
    "order_id",
    "customer_email",
    "customer_name",
    "old_status",
    "new_status",
    "total_amount",
    "changed_at",
)


def _send_email(event: dict) -> None:
    """Envia via SMTP (smtplib). Em dev/local, SMTP_HOST aponta para o Mailpit
    (docker-compose) — nenhum e-mail real sai, mas o fluxo roda de ponta a ponta e o
    resultado é inspecionável em http://localhost:8025."""
    host = os.environ.get("SMTP_HOST", "localhost")
    port = int(os.environ.get("SMTP_PORT", "1025"))
    from_addr = os.environ.get("SMTP_FROM", "no-reply@order-api.local")

    message = MIMEMultipart("alternative")
    message["Subject"] = f"Order #{event['order_id'][:8].upper()} — {event['new_status']}"
    message["From"] = from_addr
    message["To"] = event["customer_email"]
    message.attach(MIMEText(build_order_status_email_html(event), "html"))

    with smtplib.SMTP(host, port, timeout=10) as smtp:
        smtp.send_message(message)


def _is_valid_event(payload: object) -> bool:
    return isinstance(payload, dict) and all(field in payload for field in _REQUIRED_EVENT_FIELDS)


def _retry_or_dead_letter(channel, method, properties, body, error: Exception) -> None:
    """Retry limitado com backoff fixo (2s) e header `x-retry-count`; ao esgotar
    MAX_RETRIES, a mensagem é rejeitada sem requeue e roteada para a DLQ
    (order.status.changed.dlq, configurada via x-dead-letter-exchange/routing-key na
    própria fila - ver QUEUE_ARGUMENTS). Sem esse limite, uma falha persistente (SMTP fora
    do ar, por exemplo) reprocessaria a mesma mensagem para sempre - constatado na prática
    rodando este worker contra um Mailpit temporariamente inacessível."""
    headers = dict((properties.headers or {}) if properties else {})
    retry_count = int(headers.get("x-retry-count", 0)) + 1

    if retry_count > MAX_RETRIES:
        logger.error("Exceeded %s retries, sending message to DLQ", MAX_RETRIES, exc_info=error)
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        return

    logger.warning(
        "Failed to process message (attempt %s/%s), retrying: %s", retry_count, MAX_RETRIES, error
    )
    time.sleep(RETRY_BACKOFF_SECONDS)
    headers["x-retry-count"] = retry_count
    channel.basic_publish(
        exchange="",
        routing_key=ORDER_STATUS_CHANGED_QUEUE,
        body=body,
        properties=pika.BasicProperties(content_type="application/json", delivery_mode=2, headers=headers),
    )
    channel.basic_ack(delivery_tag=method.delivery_tag)


def _handle_message(channel, method, properties, body) -> None:
    try:
        event = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        logger.error("Malformed order status message, sending to DLQ: %s", error)
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        return

    if not _is_valid_event(event):
        logger.error("Order status message missing required fields, sending to DLQ")
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        return

    try:
        _send_email(event)
        # Nunca logar customer_email em texto claro (mesma convenção de order_events.py).
        logger.info(
            "order_status_notification_sent: order_id=%s old_status=%s new_status=%s",
            event["order_id"],
            event["old_status"],
            event["new_status"],
        )
        channel.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as error:
        _retry_or_dead_letter(channel, method, properties, body, error)


def run() -> None:
    """Worker standalone que consome `order.status.changed` e envia a notificação por e-mail.
    Reconecta indefinidamente se o broker cair ou estiver indisponível no boot, em vez de
    encerrar o processo - roda como um processo/container de longa duração separado da API
    (`python worker.py`), nao dentro do processo do uvicorn."""
    url = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")

    while True:
        try:
            connection = pika.BlockingConnection(pika.URLParameters(url))
            channel = connection.channel()
            channel.queue_declare(queue=ORDER_STATUS_CHANGED_DLQ, durable=True)
            channel.queue_declare(queue=ORDER_STATUS_CHANGED_QUEUE, durable=True, arguments=QUEUE_ARGUMENTS)
            channel.basic_qos(prefetch_count=10)
            channel.basic_consume(queue=ORDER_STATUS_CHANGED_QUEUE, on_message_callback=_handle_message)
            logger.info("worker_started: queue=%s", ORDER_STATUS_CHANGED_QUEUE)
            channel.start_consuming()
        except KeyboardInterrupt:
            return
        except Exception:
            logger.exception("RabbitMQ connection lost, retrying in %ss", RECONNECT_DELAY_SECONDS)
            time.sleep(RECONNECT_DELAY_SECONDS)


if __name__ == "__main__":
    run()
