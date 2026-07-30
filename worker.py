import json
import logging
import os
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pika

from api.events.order_status_email import build_order_status_email_html
from api.events.rabbitmq_publisher import ORDER_STATUS_CHANGED_QUEUE

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("worker")

RECONNECT_DELAY_SECONDS = 5
REQUEUE_DELAY_SECONDS = 5


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


def _handle_message(channel, method, _properties, body) -> None:
    try:
        event = json.loads(body)
        _send_email(event)
        # Nunca logar customer_email em texto claro (mesma convenção de order_events.py).
        logger.info(
            "order_status_notification_sent: order_id=%s old_status=%s new_status=%s",
            event["order_id"],
            event["old_status"],
            event["new_status"],
        )
        channel.basic_ack(delivery_tag=method.delivery_tag)
    except Exception:
        # Sem o delay, uma falha persistente (SMTP fora do ar, por exemplo) faria a mesma
        # mensagem ser reentregue e falhar imediatamente em loop apertado, consumindo CPU e
        # inundando o log - constatado na prática rodando este worker contra um Mailpit
        # temporariamente inacessível.
        logger.exception(
            "Failed to process order status message, requeueing in %ss", REQUEUE_DELAY_SECONDS
        )
        time.sleep(REQUEUE_DELAY_SECONDS)
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


def run() -> None:
    """Worker standalone que consome `order.status.changed` e processa a notificação
    (hoje um log estruturado, equivalente ao stub de e-mail do java-order-api/nest-order-api).
    Reconecta indefinidamente se o broker cair ou estiver indisponível no boot, em vez de
    encerrar o processo - roda como um processo/container de longa duração separado da API
    (`python worker.py`), nao dentro do processo do uvicorn."""
    url = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")

    while True:
        try:
            connection = pika.BlockingConnection(pika.URLParameters(url))
            channel = connection.channel()
            channel.queue_declare(queue=ORDER_STATUS_CHANGED_QUEUE, durable=True)
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
