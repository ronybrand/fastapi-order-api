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
    """Disparado ao final de confirm()/cancel(), só quando o customer tem e-mail não-vazio
    (ver DOMAIN.md). Síncrono por decisão explícita: hoje não há serviço externo de e-mail
    integrado neste projeto de referência, então não há latência/instabilidade externa a
    desacoplar nem necessidade de retry/DLQ independente da requisição HTTP — o efeito
    colateral é local (log) e rápido. Se um serviço de notificação real for integrado,
    reavalie para mensageria assíncrona (fila/broker) seguindo o mesmo critério documentado
    na skill fastapi-feature (seção "Convenções de service" > efeito colateral novo)."""
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
