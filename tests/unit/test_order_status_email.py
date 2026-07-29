from api.events.order_status_email import build_order_status_email_html

_EVENT = {
    "order_id": "11111111-2222-3333-4444-555555555555",
    "customer_name": "Ada Lovelace",
    "old_status": "OPEN",
    "new_status": "CONFIRMED",
    "changed_at": "2026-07-28T12:00:00+00:00",
    "total_amount": "42.00",
}


def test_build_order_status_email_html_renders_event_fields():
    html = build_order_status_email_html(_EVENT)

    assert "Ada Lovelace" in html
    assert "CONFIRMED" in html
    assert "11111111".upper() in html
    assert "42.00" in html


def test_build_order_status_email_html_escapes_customer_name():
    event = dict(_EVENT, customer_name="<script>alert(1)</script>")

    html = build_order_status_email_html(event)

    assert "<script>alert(1)</script>" not in html
