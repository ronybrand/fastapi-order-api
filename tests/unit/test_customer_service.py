from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from api.dependencies.dependencies import CurrentUser
from api.models.models import Customer
from api.schemas.schemas import CustomerInput
from api.services.customer_service import CustomerService
from api.utils.custom_api_exception import CustomAPIException

CURRENT_USER = CurrentUser(id="tester", roles=["admin"])


def _customer_input(**overrides) -> CustomerInput:
    data = {
        "name": "Ada Lovelace",
        "tax_id": "AB123456",
        "passport_number": None,
        "email": "ada@example.com",
    }
    data.update(overrides)
    return CustomerInput(**data)


def test_create_customer_happy_path():
    mock_db = MagicMock(spec=Session)
    mock_db.query.return_value.filter.return_value.filter.return_value.first.return_value = None

    result = CustomerService.create(mock_db, _customer_input(), CURRENT_USER)

    assert result.tax_id == "AB123456"
    assert result.created_by == "tester"
    assert result.updated_by == "tester"
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()


def test_create_customer_duplicate_tax_id_raises_conflict():
    mock_db = MagicMock(spec=Session)
    existing = Customer(id=uuid4(), tax_id="AB123456")
    mock_db.query.return_value.filter.return_value.filter.return_value.first.return_value = existing

    with pytest.raises(CustomAPIException) as exc:
        CustomerService.create(mock_db, _customer_input(), CURRENT_USER)

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "CONFLICT-01"


def test_create_customer_duplicate_passport_raises_conflict():
    mock_db = MagicMock(spec=Session)
    existing = Customer(id=uuid4(), passport_number="ABC1234")
    # first filter chain (tax_id) finds nothing, second (passport) finds a match
    mock_db.query.return_value.filter.return_value.filter.return_value.first.side_effect = [
        None,
        existing,
    ]

    with pytest.raises(CustomAPIException) as exc:
        CustomerService.create(mock_db, _customer_input(passport_number="ABC1234"), CURRENT_USER)

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "CONFLICT-02"


def test_get_customer_not_found():
    mock_db = MagicMock(spec=Session)
    mock_db.query.return_value.filter.return_value.filter.return_value.first.return_value = None

    with pytest.raises(CustomAPIException) as exc:
        CustomerService.get(mock_db, uuid4())

    assert exc.value.status_code == 404
    assert exc.value.detail["code"] == "RESOURCE-NOT-FOUND-01"


def test_delete_customer_blocked_when_has_orders():
    mock_db = MagicMock(spec=Session)
    customer_id = uuid4()
    customer = Customer(id=customer_id, tax_id="AB123456")

    def query_side_effect(model):
        query_mock = MagicMock()
        if model is Customer:
            query_mock.filter.return_value.filter.return_value.first.return_value = customer
        else:
            query_mock.filter.return_value.count.return_value = 1
        return query_mock

    mock_db.query.side_effect = query_side_effect

    with pytest.raises(CustomAPIException) as exc:
        CustomerService.delete(mock_db, customer_id, CURRENT_USER)

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "CONFLICT-03"


def test_delete_customer_happy_path_when_no_orders():
    mock_db = MagicMock(spec=Session)
    customer_id = uuid4()
    customer = Customer(id=customer_id, tax_id="AB123456")

    def query_side_effect(model):
        query_mock = MagicMock()
        if model is Customer:
            query_mock.filter.return_value.filter.return_value.first.return_value = customer
        else:
            query_mock.filter.return_value.count.return_value = 0
        return query_mock

    mock_db.query.side_effect = query_side_effect

    CustomerService.delete(mock_db, customer_id, CURRENT_USER)

    assert customer.deleted_at is not None
    assert customer.deleted_by == "tester"
    mock_db.commit.assert_called_once()


def _chained_query_mock(first_side_effect):
    """`.filter()` returns the same mock (chainable any number of times); `.first()`
    yields `first_side_effect` values in order across calls."""
    query_mock = MagicMock()
    query_mock.filter.return_value = query_mock
    query_mock.first.side_effect = first_side_effect
    return query_mock


def test_update_customer_happy_path():
    mock_db = MagicMock(spec=Session)
    customer_id = uuid4()
    customer = Customer(id=customer_id, name="Old Name", tax_id="OLD123", email="old@example.com")
    mock_db.query.return_value = _chained_query_mock([customer, None])

    updated = CustomerService.update(
        mock_db, customer_id, _customer_input(name="New Name", tax_id="NEW123"), CURRENT_USER
    )

    assert updated.name == "New Name"
    assert updated.tax_id == "NEW123"
    assert updated.updated_by == "tester"
    mock_db.commit.assert_called_once()


def test_update_customer_duplicate_tax_id_raises_conflict():
    mock_db = MagicMock(spec=Session)
    customer_id = uuid4()
    customer = Customer(id=customer_id, name="Old Name", tax_id="OLD123")
    other_customer = Customer(id=uuid4(), tax_id="NEW123")
    mock_db.query.return_value = _chained_query_mock([customer, other_customer])

    with pytest.raises(CustomAPIException) as exc:
        CustomerService.update(mock_db, customer_id, _customer_input(tax_id="NEW123"), CURRENT_USER)

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "CONFLICT-01"
