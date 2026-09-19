import pytest
from pydantic import ValidationError

from api.schemas.schemas import ItemInput


def test_item_input_rejects_blank_description():
    with pytest.raises(ValidationError):
        ItemInput(description="   ", unit_price=10, quantity=1)


def test_item_input_rejects_unit_price_with_more_than_two_decimal_places():
    with pytest.raises(ValidationError):
        ItemInput(description="Widget", unit_price="10.999", quantity=1)


def test_item_input_accepts_valid_payload():
    item = ItemInput(description="Widget", unit_price="10.99", quantity=1)

    assert item.description == "Widget"
