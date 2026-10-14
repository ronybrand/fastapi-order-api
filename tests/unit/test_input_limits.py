from decimal import Decimal

import pytest
from pydantic import ValidationError

from api.schemas.schemas import CustomerInput, ItemInput, ItemQuantityUpdate
from api.utils.field_limits import (
    MAX_EMAIL_LENGTH,
    MAX_NAME_LENGTH,
    MAX_QUANTITY,
    MAX_UNIT_PRICE,
)


def _customer(**overrides) -> CustomerInput:
    payload = {"name": "Ana", "tax_id": "AB123456", "passport_number": None, "email": "ana@example.com"}
    payload.update(overrides)
    return CustomerInput(**payload)


# --- customer name / e-mail ---
def test_name_at_the_column_limit_is_accepted():
    assert len(_customer(name="a" * MAX_NAME_LENGTH).name) == MAX_NAME_LENGTH


def test_name_above_the_limit_is_rejected():
    with pytest.raises(ValidationError):
        _customer(name="a" * (MAX_NAME_LENGTH + 1))


@pytest.mark.parametrize("name", ["", "   ", "\t\n"])
def test_blank_name_is_rejected(name):
    with pytest.raises(ValidationError):
        _customer(name=name)


def test_email_above_the_limit_is_rejected():
    local = "a" * (MAX_EMAIL_LENGTH - len("@example.com") + 1)

    with pytest.raises(ValidationError):
        _customer(email=f"{local}@example.com")


# --- tax_id canonical form ---
@pytest.mark.parametrize(
    ("raw", "canonical"),
    [("123.456-78", "12345678"), ("ab-12.cd/9", "AB12CD9"), ("abcde", "ABCDE"), ("AB123456", "AB123456")],
)
def test_tax_id_is_stored_in_canonical_form(raw, canonical):
    assert _customer(tax_id=raw).tax_id == canonical


@pytest.mark.parametrize("raw", [".....", "A.B-C", "-./-.-", "ab.c"])
def test_tax_id_with_fewer_than_five_letters_or_digits_is_rejected(raw):
    with pytest.raises(ValidationError):
        _customer(tax_id=raw)


def test_formatting_differences_collapse_into_the_same_document():
    assert _customer(tax_id="123.456-78").tax_id == _customer(tax_id="12345678").tax_id


# --- unit price / quantity ---
def test_unit_price_at_the_column_limit_is_accepted():
    assert ItemInput(description="x", unit_price=MAX_UNIT_PRICE, quantity=1).unit_price == MAX_UNIT_PRICE


def test_unit_price_above_the_column_limit_is_rejected():
    with pytest.raises(ValidationError):
        ItemInput(description="x", unit_price=MAX_UNIT_PRICE + Decimal("0.01"), quantity=1)


def test_quantity_at_the_limit_is_accepted():
    assert ItemInput(description="x", unit_price=1, quantity=MAX_QUANTITY).quantity == MAX_QUANTITY


def test_quantity_above_the_limit_is_rejected():
    with pytest.raises(ValidationError):
        ItemInput(description="x", unit_price=1, quantity=MAX_QUANTITY + 1)


def test_quantity_update_above_the_limit_is_rejected():
    with pytest.raises(ValidationError):
        ItemQuantityUpdate(quantity=MAX_QUANTITY + 1)


def test_quantity_update_at_the_limit_is_accepted():
    assert ItemQuantityUpdate(quantity=MAX_QUANTITY).quantity == MAX_QUANTITY
