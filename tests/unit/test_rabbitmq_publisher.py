import json
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import pytest

from api.events.order_events import OrderStatusChangedEvent
from api.events.rabbitmq_publisher import ORDER_STATUS_CHANGED_QUEUE, _json_default, publish_to_rabbitmq
from api.models.models import OrderStatus

_EVENT = OrderStatusChangedEvent(
    order_id=uuid4(),
    customer_email="ada@example.com",
    customer_name="Ada Lovelace",
    old_status=OrderStatus.OPEN,
    new_status=OrderStatus.CONFIRMED,
    total_amount=Decimal("42.00"),
    changed_at=datetime.now(UTC),
)


def test_publish_declares_queue_and_publishes_json_body():
    with patch("api.events.rabbitmq_publisher.pika.BlockingConnection") as connection_cls:
        connection = connection_cls.return_value
        channel = connection.channel.return_value

        publish_to_rabbitmq(_EVENT)

    channel.queue_declare.assert_called_once_with(queue=ORDER_STATUS_CHANGED_QUEUE, durable=True)
    channel.basic_publish.assert_called_once()
    body = channel.basic_publish.call_args.kwargs["body"]
    payload = json.loads(body)
    assert payload["order_id"] == str(_EVENT.order_id)
    assert payload["old_status"] == "OPEN"
    assert payload["new_status"] == "CONFIRMED"
    connection.close.assert_called_once()


def test_publish_swallows_connection_errors():
    with patch("api.events.rabbitmq_publisher.pika.BlockingConnection", side_effect=RuntimeError("down")):
        publish_to_rabbitmq(_EVENT)  # não deve levantar


def test_publish_closes_connection_even_if_publish_fails():
    with patch("api.events.rabbitmq_publisher.pika.BlockingConnection") as connection_cls:
        connection = connection_cls.return_value
        channel = connection.channel.return_value
        channel.basic_publish.side_effect = RuntimeError("boom")

        publish_to_rabbitmq(_EVENT)  # não deve levantar

    connection.close.assert_called_once()


def test_json_default_rejects_unknown_types():
    class Unsupported:
        pass

    with pytest.raises(TypeError):
        _json_default(Unsupported())
