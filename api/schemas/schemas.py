from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from api.models.models import OrderStatus
from api.utils.field_limits import (
    MAX_EMAIL_LENGTH,
    MAX_NAME_LENGTH,
    MAX_QUANTITY,
    MAX_UNIT_PRICE,
    MIN_TAX_ID_SIGNIFICANT_CHARS,
)
from api.utils.max_items import MAX_ITEMS_PER_ORDER
from api.utils.search_limits import (
    MAX_CONDITIONS_PER_FIELD,
    MAX_FILTER_FIELDS,
    MAX_IN_VALUES,
    MAX_OFFSET,
    MAX_VALUE_LENGTH,
)


class DefaultErrorResponse(BaseModel):
    message: str
    code: str
    params: dict


# --- SEARCH ---
class FilterOperator(StrEnum):
    eq = "eq"
    neq = "neq"
    gt = "gt"
    gte = "gte"
    lt = "lt"
    lte = "lte"
    in_ = "in"
    between = "between"
    lk = "lk"


def _check_filter_value(value: object) -> None:
    if isinstance(value, list):
        if len(value) > MAX_IN_VALUES:
            raise ValueError(f"a filter list accepts at most {MAX_IN_VALUES} values")
        for item in value:
            _check_filter_value(item)
    elif isinstance(value, str) and len(value) > MAX_VALUE_LENGTH:
        raise ValueError(f"a filter value accepts at most {MAX_VALUE_LENGTH} characters")


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page: int = Field(default=0, ge=0)
    size: int = Field(default=20, ge=1, le=100)
    sort: str | None = None
    filters: dict[str, list[dict]] | None = None

    @model_validator(mode="after")
    def within_search_limits(self) -> "SearchRequest":
        if self.page * self.size > MAX_OFFSET:
            raise ValueError("page is too large")
        filters = self.filters or {}
        if len(filters) > MAX_FILTER_FIELDS:
            raise ValueError(f"filters accepts at most {MAX_FILTER_FIELDS} fields")
        for conditions in filters.values():
            if len(conditions) > MAX_CONDITIONS_PER_FIELD:
                raise ValueError(f"a filter field accepts at most {MAX_CONDITIONS_PER_FIELD} conditions")
            for condition in conditions:
                _check_filter_value(condition.get("value"))
        return self


class PaginatedResponse[T](BaseModel):
    items: list[T]
    total: int
    page: int
    size: int


# --- CUSTOMER ---
class CustomerInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=MAX_NAME_LENGTH)
    tax_id: str = Field(pattern=r"^[A-Za-z0-9./-]{5,20}$")
    passport_number: str | None = Field(default=None, pattern=r"^[A-Z0-9]{6,9}$")
    email: EmailStr

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be blank")
        return value

    @field_validator("email")
    @classmethod
    def email_within_column_limit(cls, value: str) -> str:
        if len(value) > MAX_EMAIL_LENGTH:
            raise ValueError(f"email must have at most {MAX_EMAIL_LENGTH} characters")
        return value

    @field_validator("tax_id")
    @classmethod
    def canonical_tax_id(cls, value: str) -> str:
        """Pontuacao e caixa sao formatacao, nao identidade: "123.456-78" e "12345678" sao o mesmo
        documento, entao o valor gravado (e comparado pela unicidade) e sempre a forma canonica."""
        canonical = "".join(char for char in value if char.isalnum()).upper()
        if len(canonical) < MIN_TAX_ID_SIGNIFICANT_CHARS:
            raise ValueError(f"tax_id must contain at least {MIN_TAX_ID_SIGNIFICANT_CHARS} letters or digits")
        return canonical


class CustomerResponse(BaseModel):
    # tax_id, passport_number e email nunca sao expostos aqui de proposito: sao PII e
    # nenhum consumidor desta API precisa deles de volta na resposta (o cliente que criou
    # o registro ja tem esses valores, e nao existe hoje um caminho de UI/integracao que
    # precise reexibi-los). Ver api/utils/sensitive.py - mask_sensitive() cobre o caso de
    # log, este comentario cobre o caso de resposta HTTP.
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str


# --- ITEM ---
class ItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str = Field(min_length=1, max_length=255)
    unit_price: Decimal = Field(gt=0, le=MAX_UNIT_PRICE)
    quantity: int = Field(gt=0, le=MAX_QUANTITY)

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
    model_config = ConfigDict(extra="forbid")
    quantity: int = Field(gt=0, le=MAX_QUANTITY)


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
    model_config = ConfigDict(extra="forbid")
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
