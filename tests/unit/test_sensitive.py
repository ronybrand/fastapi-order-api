from uuid import uuid4

from pydantic import BaseModel, Field

from api.models.models import Customer
from api.utils.sensitive import REDACTED, mask_sensitive


def test_mask_sensitive_redacts_sqlalchemy_model_columns():
    customer = Customer(
        id=uuid4(),
        name="Ada Lovelace",
        tax_id="AB123456",
        passport_number="P123",
        email="ada@example.com",
    )

    masked = mask_sensitive(customer)

    assert masked["name"] == "Ada Lovelace"
    assert masked["tax_id"] == REDACTED
    assert masked["passport_number"] == REDACTED
    assert masked["email"] == REDACTED


def test_mask_sensitive_skips_none_sensitive_column():
    customer = Customer(id=uuid4(), name="Ada Lovelace", tax_id="AB123456", passport_number=None)

    masked = mask_sensitive(customer)

    assert masked["passport_number"] is None


class _SensitiveSchema(BaseModel):
    name: str
    secret: str = Field(json_schema_extra={"sensitive": True})


def test_mask_sensitive_redacts_pydantic_model_fields():
    obj = _SensitiveSchema(name="Ada", secret="topsecret")

    masked = mask_sensitive(obj)

    assert masked["name"] == "Ada"
    assert masked["secret"] == REDACTED


def test_mask_sensitive_skips_none_sensitive_field():
    class SchemaWithOptionalSecret(BaseModel):
        name: str
        secret: str | None = Field(default=None, json_schema_extra={"sensitive": True})

    obj = SchemaWithOptionalSecret(name="Ada", secret=None)

    masked = mask_sensitive(obj)

    assert masked["secret"] is None


def test_mask_sensitive_returns_object_unchanged_when_not_model():
    obj = object()

    assert mask_sensitive(obj) is obj
