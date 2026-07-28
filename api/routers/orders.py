from uuid import UUID

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from api.dependencies.dependencies import CurrentUser, get_current_user, get_db
from api.schemas.schemas import (
    DefaultErrorResponse,
    ItemInput,
    ItemQuantityUpdate,
    OrderCreate,
    OrderResponse,
    PaginatedResponse,
    SearchRequest,
)
from api.services.order_service import OrderService

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post(
    "",
    response_model=OrderResponse,
    status_code=201,
    summary="Create a new order",
    responses={
        400: {"model": DefaultErrorResponse, "description": "Validation error / customer not found"},
    },
)
def create_order(
    order: OrderCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Creates an order for an existing customer with an initial list of items."""
    return OrderService.create(db, order, current_user)


# As rotas de busca (`/search`) precisam ser declaradas antes de `/{order_id}`: um path
# estático depois de um dinâmico nunca é alcançado — `/orders/search` casaria com
# `/{order_id}` (order_id="search") e falharia a validação de UUID antes de chegar aqui.
@router.get(
    "/search", response_model=PaginatedResponse[OrderResponse], summary="Search orders via query params"
)
def search_orders_get(
    search: SearchRequest = Depends(),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Searches orders using page/size/sort query params."""
    items, total = OrderService.search(db, search)
    return PaginatedResponse(items=items, total=total, page=search.page, size=search.size)


@router.post(
    "/search", response_model=PaginatedResponse[OrderResponse], summary="Search orders via request body"
)
def search_orders_post(
    search: SearchRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Searches orders, accepting the full `filters` payload in the request body."""
    items, total = OrderService.search(db, search)
    return PaginatedResponse(items=items, total=total, page=search.page, size=search.size)


@router.get(
    "/{order_id}",
    response_model=OrderResponse,
    summary="Get order by ID",
    responses={404: {"model": DefaultErrorResponse, "description": "Order not found"}},
)
def get_order(
    order_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Retrieves an order by id, including its items and calculated total."""
    return OrderService.get(db, order_id)


@router.delete(
    "/{order_id}",
    status_code=204,
    summary="Delete order",
    responses={404: {"model": DefaultErrorResponse, "description": "Order not found"}},
)
def delete_order(
    order_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Soft-deletes an order."""
    OrderService.delete(db, order_id, current_user)


@router.post(
    "/{order_id}/items",
    response_model=OrderResponse,
    summary="Add an item to an order",
    responses={
        400: {"model": DefaultErrorResponse, "description": "Order is not editable"},
        404: {"model": DefaultErrorResponse, "description": "Order not found"},
        409: {"model": DefaultErrorResponse, "description": "Concurrent modification"},
    },
)
def add_item(
    item: ItemInput,
    order_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Adds a line item to an order. Requires the order to be OPEN."""
    return OrderService.add_item(db, order_id, item, current_user)


@router.patch(
    "/{order_id}/items/{item_id}",
    response_model=OrderResponse,
    summary="Update a line item's quantity",
    responses={
        400: {"model": DefaultErrorResponse, "description": "Order is not editable"},
        404: {"model": DefaultErrorResponse, "description": "Order or item not found"},
        409: {"model": DefaultErrorResponse, "description": "Concurrent modification"},
    },
)
def update_item_quantity(
    quantity: ItemQuantityUpdate,
    order_id: UUID = Path(...),
    item_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Updates the quantity of an existing line item. Requires the order to be OPEN."""
    return OrderService.update_item_quantity(db, order_id, item_id, quantity.quantity, current_user)


@router.delete(
    "/{order_id}/items/{item_id}",
    response_model=OrderResponse,
    summary="Remove an item from an order",
    responses={
        400: {"model": DefaultErrorResponse, "description": "Order is not editable"},
        404: {"model": DefaultErrorResponse, "description": "Order or item not found"},
        409: {"model": DefaultErrorResponse, "description": "Concurrent modification"},
    },
)
def remove_item(
    order_id: UUID = Path(...),
    item_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Removes a line item from an order. Requires the order to be OPEN."""
    return OrderService.remove_item(db, order_id, item_id, current_user)


@router.post(
    "/{order_id}/confirm",
    response_model=OrderResponse,
    summary="Confirm an order",
    responses={
        400: {"model": DefaultErrorResponse, "description": "Invalid transition / order is empty"},
        404: {"model": DefaultErrorResponse, "description": "Order not found"},
        409: {"model": DefaultErrorResponse, "description": "Concurrent modification"},
    },
)
def confirm_order(
    order_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Transitions an order from OPEN to CONFIRMED. Fails if empty or not OPEN."""
    return OrderService.confirm(db, order_id, current_user)


@router.post(
    "/{order_id}/cancel",
    response_model=OrderResponse,
    summary="Cancel an order",
    responses={
        400: {"model": DefaultErrorResponse, "description": "Order is already canceled"},
        404: {"model": DefaultErrorResponse, "description": "Order not found"},
        409: {"model": DefaultErrorResponse, "description": "Concurrent modification"},
    },
)
def cancel_order(
    order_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Transitions an order from OPEN or CONFIRMED to CANCELED."""
    return OrderService.cancel(db, order_id, current_user)
