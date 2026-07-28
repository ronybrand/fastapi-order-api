from uuid import UUID

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from api.dependencies.dependencies import CurrentUser, get_current_user, get_db, require_role
from api.schemas.schemas import (
    CustomerInput,
    CustomerResponse,
    DefaultErrorResponse,
    PaginatedResponse,
    SearchRequest,
)
from api.security.roles import ROLE_ADMIN
from api.services.customer_service import CustomerService

router = APIRouter(prefix="/customers", tags=["customers"])


@router.post(
    "",
    response_model=CustomerResponse,
    status_code=201,
    summary="Create a new customer",
    responses={
        400: {"model": DefaultErrorResponse, "description": "VALIDATION-01 (request schema)"},
        409: {
            "model": DefaultErrorResponse,
            "description": "CONFLICT-01 (tax_id exists) / CONFLICT-02 (passport_number exists)",
        },
    },
)
def create_customer(
    customer: CustomerInput,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(ROLE_ADMIN)),
):
    """Creates a new customer, validating tax_id/passport_number uniqueness."""
    return CustomerService.create(db, customer, current_user)


# As rotas de busca (`/search`) precisam ser declaradas antes de `/{customer_id}`: o FastAPI
# resolve rotas na ordem de registro, e um path estático depois de um dinâmico nunca é
# alcançado — `/customers/search` casaria com `/{customer_id}` (customer_id="search") e
# falharia a validação de UUID antes de chegar aqui.
@router.get(
    "/search",
    response_model=PaginatedResponse[CustomerResponse],
    summary="Search customers via query params",
)
def search_customers_get(
    search: SearchRequest = Depends(),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Searches customers using page/size/sort query params (no `filters`, use POST /search
    for filter conditions — a dict of dicts is not expressible as flat query params)."""
    items, total = CustomerService.search(db, search)
    return PaginatedResponse(items=items, total=total, page=search.page, size=search.size)


@router.post(
    "/search",
    response_model=PaginatedResponse[CustomerResponse],
    summary="Search customers via request body",
)
def search_customers_post(
    search: SearchRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Searches customers, accepting the full `filters` payload in the request body."""
    items, total = CustomerService.search(db, search)
    return PaginatedResponse(items=items, total=total, page=search.page, size=search.size)


@router.get(
    "/{customer_id}",
    response_model=CustomerResponse,
    summary="Get customer by ID",
    responses={404: {"model": DefaultErrorResponse, "description": "RESOURCE-NOT-FOUND-01"}},
)
def get_customer(
    customer_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Retrieves a customer by id."""
    return CustomerService.get(db, customer_id)


@router.put(
    "/{customer_id}",
    response_model=CustomerResponse,
    summary="Update customer",
    responses={
        400: {"model": DefaultErrorResponse, "description": "VALIDATION-01 (request schema)"},
        404: {"model": DefaultErrorResponse, "description": "RESOURCE-NOT-FOUND-01"},
        409: {
            "model": DefaultErrorResponse,
            "description": "CONFLICT-01 (tax_id exists) / CONFLICT-02 (passport_number exists)",
        },
    },
)
def update_customer(
    customer: CustomerInput,
    customer_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(ROLE_ADMIN)),
):
    """Updates a customer, validating uniqueness excluding the record itself."""
    return CustomerService.update(db, customer_id, customer, current_user)


@router.delete(
    "/{customer_id}",
    status_code=204,
    summary="Delete customer",
    responses={
        404: {"model": DefaultErrorResponse, "description": "RESOURCE-NOT-FOUND-01"},
        409: {"model": DefaultErrorResponse, "description": "CONFLICT-03 (customer has orders)"},
    },
)
def delete_customer(
    customer_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(ROLE_ADMIN)),
):
    """Soft-deletes a customer. Blocked if the customer still has non-deleted orders."""
    CustomerService.delete(db, customer_id, current_user)
