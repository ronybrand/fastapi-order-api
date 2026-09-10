from tests.utils.auth import admin_headers, auth_headers, invalid_audience_headers


def _customer_payload(**overrides):
    payload = {
        "name": "Ada Lovelace",
        "tax_id": "AB123456",
        "passport_number": None,
        "email": "ada@example.com",
    }
    payload.update(overrides)
    return payload


def test_create_customer_is_rate_limited_tighter_than_the_global_default(client):
    # POST /customers tem limite proprio de 10/minute (ver customers.py), mais apertado
    # que o default global de 100/minute - as 10 primeiras passam (podem falhar por outro
    # motivo, tanto faz), a 11a tem que ser 429 especificamente por rate limit.
    for _ in range(10):
        client.post(
            "/customers", json=_customer_payload(tax_id=f"RATE-{_}"), headers=admin_headers()
        )

    response = client.post(
        "/customers", json=_customer_payload(tax_id="RATE-OVER-LIMIT"), headers=admin_headers()
    )

    assert response.status_code == 429
    assert response.json()["code"] == "RATE-00"


def test_create_customer_requires_admin_role(client):
    response = client.post("/customers", json=_customer_payload(), headers=auth_headers())
    assert response.status_code == 403


def test_create_customer_requires_authentication(client):
    response = client.post("/customers", json=_customer_payload())
    assert response.status_code == 401


def test_create_customer_rejects_invalid_audience(client):
    response = client.post("/customers", json=_customer_payload(), headers=invalid_audience_headers())
    assert response.status_code == 401


def test_create_and_get_customer(client):
    create_response = client.post("/customers", json=_customer_payload(), headers=admin_headers())
    assert create_response.status_code == 201
    customer_id = create_response.json()["id"]

    get_response = client.get(f"/customers/{customer_id}", headers=auth_headers())
    assert get_response.status_code == 200
    assert get_response.json()["name"] == "Ada Lovelace"
    # tax_id/passport_number/email sao PII e nunca aparecem na resposta (ver
    # CustomerResponse) - nem para quem acabou de criar o registro.
    assert "tax_id" not in get_response.json()
    assert "passport_number" not in get_response.json()
    assert "email" not in get_response.json()


def test_create_customer_duplicate_tax_id_returns_conflict(client):
    client.post("/customers", json=_customer_payload(), headers=admin_headers())
    response = client.post(
        "/customers", json=_customer_payload(email="other@example.com"), headers=admin_headers()
    )

    assert response.status_code == 409
    assert response.json()["code"] == "CONFLICT-01"


def test_get_customer_not_found(client):
    response = client.get("/customers/00000000-0000-0000-0000-000000000000", headers=auth_headers())
    assert response.status_code == 404
    assert response.json()["code"] == "RESOURCE-NOT-FOUND-01"


def test_delete_customer_blocked_when_has_order(client):
    customer_id = client.post("/customers", json=_customer_payload(), headers=admin_headers()).json()["id"]
    client.post("/orders", json={"customer_id": customer_id, "items": []}, headers=auth_headers())

    response = client.delete(f"/customers/{customer_id}", headers=admin_headers())

    assert response.status_code == 409
    assert response.json()["code"] == "CONFLICT-03"


def test_customer_search_via_get(client):
    client.post("/customers", json=_customer_payload(), headers=admin_headers())

    response = client.get("/customers/search", params={"page": 0, "size": 20}, headers=auth_headers())

    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 0
    assert body["size"] == 20
    assert len(body["items"]) >= 1
