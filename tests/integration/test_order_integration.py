from tests.utils.auth import admin_headers, auth_headers


def _create_customer(client, tax_id="AB123456", email="ada@example.com"):
    payload = {"name": "Ada Lovelace", "tax_id": tax_id, "passport_number": None, "email": email}
    return client.post("/customers", json=payload, headers=admin_headers()).json()["id"]


def _create_order(client, customer_id, items=None):
    payload = {"customer_id": customer_id, "items": items or []}
    return client.post("/orders", json=payload, headers=auth_headers()).json()


def test_create_order_requires_authentication(client):
    payload = {"customer_id": "00000000-0000-0000-0000-000000000000", "items": []}
    response = client.post("/orders", json=payload)
    assert response.status_code == 401


def test_create_order_with_invalid_customer_returns_validation_error(client):
    payload = {"customer_id": "00000000-0000-0000-0000-000000000000", "items": []}
    response = client.post("/orders", json=payload, headers=auth_headers())
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION-07"


def test_create_order_and_confirm_flow(client):
    customer_id = _create_customer(client)
    items = [{"description": "Widget", "unit_price": "10.00", "quantity": 2}]

    order = _create_order(client, customer_id, items)
    assert order["status"] == "OPEN"
    assert order["total"] == "20.00"

    confirm_response = client.post(f"/orders/{order['id']}/confirm", headers=auth_headers())
    assert confirm_response.status_code == 200
    assert confirm_response.json()["status"] == "CONFIRMED"


def test_confirm_empty_order_returns_validation_error(client):
    customer_id = _create_customer(client)
    order = _create_order(client, customer_id)

    response = client.post(f"/orders/{order['id']}/confirm", headers=auth_headers())

    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION-03"


def test_cannot_edit_items_after_confirm(client):
    customer_id = _create_customer(client)
    items = [{"description": "Widget", "unit_price": "10.00", "quantity": 1}]
    order = _create_order(client, customer_id, items)
    client.post(f"/orders/{order['id']}/confirm", headers=auth_headers())

    response = client.post(
        f"/orders/{order['id']}/items",
        json={"description": "Extra", "unit_price": "5.00", "quantity": 1},
        headers=auth_headers(),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION-02"


def test_cancel_already_canceled_order_returns_validation_error(client):
    customer_id = _create_customer(client)
    order = _create_order(client, customer_id)
    client.post(f"/orders/{order['id']}/cancel", headers=auth_headers())

    response = client.post(f"/orders/{order['id']}/cancel", headers=auth_headers())

    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION-04"


def test_add_update_remove_item_flow(client):
    customer_id = _create_customer(client)
    order = _create_order(client, customer_id)

    add_response = client.post(
        f"/orders/{order['id']}/items",
        json={"description": "Widget", "unit_price": "10.00", "quantity": 1},
        headers=auth_headers(),
    )
    assert add_response.status_code == 200
    item_id = add_response.json()["items"][0]["id"]

    update_response = client.patch(
        f"/orders/{order['id']}/items/{item_id}", json={"quantity": 3}, headers=auth_headers()
    )
    assert update_response.status_code == 200
    assert update_response.json()["items"][0]["quantity"] == 3

    remove_response = client.delete(f"/orders/{order['id']}/items/{item_id}", headers=auth_headers())
    assert remove_response.status_code == 200
    assert remove_response.json()["items"] == []


def test_order_item_not_found_returns_404(client):
    customer_id = _create_customer(client)
    order = _create_order(client, customer_id)

    response = client.patch(
        f"/orders/{order['id']}/items/00000000-0000-0000-0000-000000000000",
        json={"quantity": 3},
        headers=auth_headers(),
    )

    assert response.status_code == 404
    assert response.json()["code"] == "RESOURCE-NOT-FOUND-03"


def test_max_items_per_order_limit(client):
    customer_id = _create_customer(client)
    items = [{"description": f"Item {i}", "unit_price": "1.00", "quantity": 1} for i in range(201)]

    response = client.post(
        "/orders", json={"customer_id": customer_id, "items": items}, headers=auth_headers()
    )

    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION-01"
