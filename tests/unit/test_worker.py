import json
from unittest.mock import MagicMock, patch

from worker import MAX_RETRIES, _handle_message, _send_email, run

_EVENT = {
    "order_id": "11111111-2222-3333-4444-555555555555",
    "customer_email": "ada@example.com",
    "customer_name": "Ada Lovelace",
    "old_status": "OPEN",
    "new_status": "CONFIRMED",
    "total_amount": "42.00",
    "changed_at": "2026-07-28T12:00:00+00:00",
}


def test_send_email_builds_and_sends_message():
    with patch("worker.smtplib.SMTP") as smtp_cls:
        smtp = smtp_cls.return_value.__enter__.return_value
        _send_email(_EVENT)

    smtp_cls.assert_called_once()
    smtp.send_message.assert_called_once()
    sent_message = smtp.send_message.call_args[0][0]
    assert sent_message["To"] == "ada@example.com"
    assert "CONFIRMED" in sent_message["Subject"]


def test_handle_message_acks_on_success():
    channel = MagicMock()
    method = MagicMock(delivery_tag=1)
    properties = MagicMock(headers=None)

    with patch("worker._send_email") as send_email:
        _handle_message(channel, method, properties, json.dumps(_EVENT).encode())

    send_email.assert_called_once_with(_EVENT)
    channel.basic_ack.assert_called_once_with(delivery_tag=1)
    channel.basic_nack.assert_not_called()


def test_handle_message_retries_with_incremented_header_on_first_failures():
    channel = MagicMock()
    method = MagicMock(delivery_tag=2)
    properties = MagicMock(headers={"x-retry-count": 1})

    with patch("worker._send_email", side_effect=RuntimeError("smtp down")), patch("worker.time.sleep"):
        _handle_message(channel, method, properties, json.dumps(_EVENT).encode())

    channel.basic_nack.assert_not_called()
    channel.basic_ack.assert_called_once_with(delivery_tag=2)
    republish_kwargs = channel.basic_publish.call_args.kwargs
    assert republish_kwargs["routing_key"] == "order.status.changed"
    assert republish_kwargs["properties"].headers["x-retry-count"] == 2


def test_handle_message_sends_to_dlq_after_exceeding_max_retries():
    channel = MagicMock()
    method = MagicMock(delivery_tag=3)
    properties = MagicMock(headers={"x-retry-count": MAX_RETRIES})

    with patch("worker._send_email", side_effect=RuntimeError("smtp down")), patch("worker.time.sleep"):
        _handle_message(channel, method, properties, json.dumps(_EVENT).encode())

    channel.basic_publish.assert_not_called()
    channel.basic_ack.assert_not_called()
    channel.basic_nack.assert_called_once_with(delivery_tag=3, requeue=False)


def test_handle_message_sends_malformed_body_straight_to_dlq():
    channel = MagicMock()
    method = MagicMock(delivery_tag=4)
    properties = MagicMock(headers=None)

    _handle_message(channel, method, properties, b"not-json")

    channel.basic_nack.assert_called_once_with(delivery_tag=4, requeue=False)
    channel.basic_ack.assert_not_called()
    channel.basic_publish.assert_not_called()


def test_handle_message_sends_event_missing_fields_straight_to_dlq():
    channel = MagicMock()
    method = MagicMock(delivery_tag=5)
    properties = MagicMock(headers=None)
    incomplete_event = {"order_id": "11111111-2222-3333-4444-555555555555"}

    _handle_message(channel, method, properties, json.dumps(incomplete_event).encode())

    channel.basic_nack.assert_called_once_with(delivery_tag=5, requeue=False)
    channel.basic_ack.assert_not_called()


def test_run_exits_cleanly_on_keyboard_interrupt():
    with patch("worker.pika.BlockingConnection", side_effect=KeyboardInterrupt):
        run()  # não deve levantar


def test_run_reconnects_after_connection_failure_then_exits():
    connect = patch(
        "worker.pika.BlockingConnection", side_effect=[RuntimeError("broker down"), KeyboardInterrupt]
    )
    with connect, patch("worker.time.sleep") as sleep:
        run()

    sleep.assert_called_once_with(5)


def test_run_declares_queues_with_dead_letter_args_and_starts_consuming():
    connection = MagicMock()
    channel = connection.channel.return_value
    channel.start_consuming.side_effect = KeyboardInterrupt

    with patch("worker.pika.BlockingConnection", return_value=connection):
        run()

    assert channel.queue_declare.call_count == 2
    channel.queue_declare.assert_any_call(queue="order.status.changed.dlq", durable=True)
    channel.queue_declare.assert_any_call(
        queue="order.status.changed",
        durable=True,
        arguments={
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": "order.status.changed.dlq",
        },
    )
    channel.basic_consume.assert_called_once()
