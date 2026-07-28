from decimal import Decimal
from enum import Enum
from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from api.models.models import OrderStatus
from api.utils.max_items import MAX_ITEMS_PER_ORDER

T = TypeVar("T")


class DefaultErrorResponse(BaseModel):
    message: str
    code: str
    params: dict


# --- SEARCH ---
class FilterOperator(str, Enum):
    eq = "eq"
    neq = "neq"
    gt = "gt"
    gte = "gte"
    lt = "lt"
    lte = "lte"
    in_ = "in"
    between = "between"
    lk = "lk"


class SearchRequest(BaseModel):
    page: int = Field(default=0, ge=0)
    size: int = Field(default=20, ge=1, le=100)
    sort: str | None = None
    filters: dict[str, list[dict]] | None = None


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    size: int


# --- CUSTOMER ---
class CustomerInput(BaseModel):
    name: str = Field(min_length=1)
    tax_id: str = Field(pattern=r"^[A-Za-z0-9./-]{5,20}$")
    passport_number: str | None = Field(default=None, pattern=r"^[A-Z0-9]{6,9}$")
    email: EmailStr


class CustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    tax_id: str
    passport_number: str | None
    email: EmailStr


# --- ITEM ---
class ItemInput(BaseModel):
    description: str = Field(min_length=1, max_length=255)
    unit_price: Decimal = Field(gt=0)
    quantity: int = Field(gt=0)

    @field_validator("description")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("description must not be blank")
        return value

    @field_validator("unit_price")
    @classmethod
    def max_two_decimal_places(cls, value: Decimal) -> Decimal:
        exponent = value.as_tuple().exponent
        if not isinstance(exponent, int) or -exponent > 2:
            raise ValueError("unit_price must have at most 2 decimal places")
        return value


class ItemQuantityUpdate(BaseModel):
    quantity: int = Field(gt=0)


class ItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    order_id: UUID
    description: str
    unit_price: Decimal
    quantity: int
    subtotal: Decimal


# --- ORDER ---
class OrderCreate(BaseModel):
    customer_id: UUID
    items: list[ItemInput] = Field(default_factory=list, max_length=MAX_ITEMS_PER_ORDER)


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    customer_id: UUID
    status: OrderStatus
    version: int
    items: list[ItemResponse]
    total: Decimal
