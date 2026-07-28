import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from api.models.models import OrderStatus

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OrderStatusChangedEvent:
    order_id: UUID
    customer_email: str
    customer_name: str
    old_status: OrderStatus
    new_status: OrderStatus
    total_amount: Decimal
    changed_at: datetime


def publish_order_status_changed(event: OrderStatusChangedEvent) -> None:
    """Disparado ao final de confirm()/cancel(), só quando o customer tem e-mail não-vazio.
    Publica no RabbitMQ para processamento assíncrono pelo worker (ver worker.py, que
    envia/loga a notificação). A publicação roda depois do commit já ter acontecido (ver
    order_service.py) e nunca propaga falha de broker para a requisição HTTP (ver
    rabbitmq_publisher.publish_to_rabbitmq)."""
    if not event.customer_email:
        return

    # Nunca logar o e-mail em texto claro (dado sensível, ver skill fastapi-feature > "Dados
    # sensíveis") — o id do order já é suficiente para rastreabilidade; quem precisar do
    # e-mail de fato consulta o customer via endpoint autorizado.
    logger.info(
        "order_status_changed: order_id=%s old_status=%s new_status=%s total=%s notified=true",
        event.order_id,
        event.old_status,
        event.new_status,
        event.total_amount,
    )

    # Import local para evitar dependência circular (rabbitmq_publisher importa
    # OrderStatusChangedEvent deste mesmo módulo).
    from api.events.rabbitmq_publisher import publish_to_rabbitmq

    publish_to_rabbitmq(event)


def build_order_status_changed_event(order, old_status: OrderStatus) -> OrderStatusChangedEvent:
    return OrderStatusChangedEvent(
        order_id=order.id,
        customer_email=order.customer.email,
        customer_name=order.customer.name,
        old_status=old_status,
        new_status=order.status,
        total_amount=order.total,
        changed_at=datetime.now(UTC),
    )
