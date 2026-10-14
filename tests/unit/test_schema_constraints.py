import pytest
from sqlalchemy import CheckConstraint, String

from api.models.models import Customer, Item, Order
from api.utils.field_limits import MAX_EMAIL_LENGTH, MAX_NAME_LENGTH


def _length(model, column: str) -> int:
    column_type = model.__table__.c[column].type
    assert isinstance(column_type, String)
    return column_type.length


@pytest.mark.parametrize(
    ("column", "expected"),
    [
        ("name", MAX_NAME_LENGTH),
        ("email", MAX_EMAIL_LENGTH),
        ("tax_id", 20),
        ("passport_number", 9),
        ("created_by", 200),
        ("updated_by", 200),
        ("deleted_by", 200),
    ],
)
def test_customer_text_columns_have_the_length_the_schemas_enforce(column, expected):
    """A String without length is unbounded text: nothing at the database stops a value the schema
    would have refused, and the limits drift apart silently. Same numbers as api/utils/field_limits.py."""
    assert _length(Customer, column) == expected


@pytest.mark.parametrize("column", ["created_by", "updated_by", "deleted_by"])
def test_audit_columns_of_orders_have_a_length_too(column):
    assert _length(Order, column) == 200


def _check_names(model) -> set[str]:
    return {c.name for c in model.__table__.constraints if isinstance(c, CheckConstraint)}


def test_item_quantity_and_price_are_checked_by_the_database_too():
    assert {"ck_items_quantity_positive", "ck_items_unit_price_positive"} <= _check_names(Item)


def test_customer_is_optimistically_locked_like_order():
    """Two concurrent PUTs on the same customer must not silently overwrite each other."""
    assert Customer.__mapper__.version_id_col is Customer.__table__.c.version
    assert Order.__mapper__.version_id_col is Order.__table__.c.version
