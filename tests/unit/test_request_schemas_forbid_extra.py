import pytest
from pydantic import ValidationError

from api.schemas.schemas import (
    CustomerInput,
    ItemInput,
    ItemQuantityUpdate,
    OrderCreate,
    SearchRequest,
)


def test_customer_input_rejects_unknown_field():
    with pytest.raises(ValidationError):
        CustomerInput(
            name="Ada Lovelace",
            tax_id="AB123456",
            email="ada@example.com",
            is_admin=True,
        )


def test_item_input_rejects_unknown_field():
    with pytest.raises(ValidationError):
        ItemInput(description="Widget", unit_price=10, quantity=1, discount=0.5)


def test_item_quantity_update_rejects_unknown_field():
    with pytest.raises(ValidationError):
        ItemQuantityUpdate(quantity=2, note="urgent")


def test_order_create_rejects_unknown_field():
    with pytest.raises(ValidationError):
        OrderCreate(customer_id="00000000-0000-0000-0000-000000000000", status="CONFIRMED")


def test_search_request_rejects_unknown_field():
    with pytest.raises(ValidationError):
        SearchRequest(page=0, size=20, limit=1000)
