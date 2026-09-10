from uuid import uuid4

from api.schemas.schemas import CustomerResponse


def _build():
    return CustomerResponse(
        id=uuid4(),
        name="Ada Lovelace",
        tax_id="AB123456",
        passport_number="P123",
        email="ada@example.com",
    )


def test_customer_response_never_serializes_tax_id():
    dumped = _build().model_dump()

    assert "tax_id" not in dumped


def test_customer_response_never_serializes_passport_number():
    dumped = _build().model_dump()

    assert "passport_number" not in dumped


def test_customer_response_never_serializes_email():
    dumped = _build().model_dump()

    assert "email" not in dumped


def test_customer_response_still_serializes_non_sensitive_fields():
    dumped = _build().model_dump()

    assert "id" in dumped
    assert dumped["name"] == "Ada Lovelace"
