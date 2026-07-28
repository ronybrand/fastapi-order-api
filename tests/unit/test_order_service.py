from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session, selectinload

from api.dependencies.dependencies import CurrentUser
from api.models.models import Customer, Item, Order, OrderStatus
from api.schemas.schemas import ItemInput, OrderCreate, SearchRequest
from api.services.order_service import OrderService
from api.utils.custom_api_exception import CustomAPIException

CURRENT_USER = CurrentUser(id="tester", roles=["user"])


def _mock_db_with_order(order: Order) -> MagicMock:
    mock_db = MagicMock(spec=Session)
    mock_db.query.return_value.filter.return_value.filter.return_value.first.return_value = order
    return mock_db


def test_create_order_happy_path():
    mock_db = MagicMock(spec=Session)
    customer = Customer(id=uuid4(), tax_id="AB123456", email="a@example.com")
    mock_db.query.return_value.filter.return_value.first.return_value = customer

    item = ItemInput(description="Widget", unit_price=10, quantity=2)
    order_in = OrderCreate(customer_id=customer.id, items=[item])
    OrderService.create(mock_db, order_in, CURRENT_USER)

    assert mock_db.add.call_count == 2  # Order + 1 Item
    mock_db.flush.assert_called_once()
    mock_db.commit.assert_called_once()


def test_create_order_invalid_customer_raises_validation_error():
    mock_db = MagicMock(spec=Session)
    mock_db.query.return_value.filter.return_value.first.return_value = None

    order_in = OrderCreate(customer_id=uuid4(), items=[])

    with pytest.raises(CustomAPIException) as exc:
        OrderService.create(mock_db, order_in, CURRENT_USER)

    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "VALIDATION-07"


def test_get_order_not_found():
    mock_db = MagicMock(spec=Session)
    mock_db.query.return_value.filter.return_value.filter.return_value.first.return_value = None

    with pytest.raises(CustomAPIException) as exc:
        OrderService.get(mock_db, uuid4())

    assert exc.value.status_code == 404
    assert exc.value.detail["code"] == "RESOURCE-NOT-FOUND-02"


def test_add_item_fails_when_order_not_open():
    order = Order(id=uuid4(), status=OrderStatus.CONFIRMED, items=[])
    mock_db = _mock_db_with_order(order)

    item = ItemInput(description="X", unit_price=1, quantity=1)
    with pytest.raises(CustomAPIException) as exc:
        OrderService.add_item(mock_db, order.id, item, CURRENT_USER)

    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "VALIDATION-02"


def test_confirm_fails_when_order_empty():
    order = Order(id=uuid4(), status=OrderStatus.OPEN, items=[])
    mock_db = _mock_db_with_order(order)

    with pytest.raises(CustomAPIException) as exc:
        OrderService.confirm(mock_db, order.id, CURRENT_USER)

    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "VALIDATION-03"


def test_confirm_fails_on_invalid_transition():
    item = Item(id=uuid4(), unit_price=Decimal("1"), quantity=1)
    order = Order(id=uuid4(), status=OrderStatus.CONFIRMED, items=[item])
    mock_db = _mock_db_with_order(order)

    with pytest.raises(CustomAPIException) as exc:
        OrderService.confirm(mock_db, order.id, CURRENT_USER)

    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "VALIDATION-04"


def test_confirm_happy_path_transitions_to_confirmed():
    customer = Customer(id=uuid4(), email="a@example.com", name="Ada")
    order = Order(
        id=uuid4(),
        status=OrderStatus.OPEN,
        items=[Item(id=uuid4(), unit_price=Decimal("1"), quantity=1)],
        customer=customer,
    )
    mock_db = _mock_db_with_order(order)

    result = OrderService.confirm(mock_db, order.id, CURRENT_USER)

    assert result.status == OrderStatus.CONFIRMED
    mock_db.commit.assert_called_once()


def test_cancel_fails_when_already_canceled():
    order = Order(id=uuid4(), status=OrderStatus.CANCELED, items=[])
    mock_db = _mock_db_with_order(order)

    with pytest.raises(CustomAPIException) as exc:
        OrderService.cancel(mock_db, order.id, CURRENT_USER)

    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "VALIDATION-04"


def test_cancel_happy_path_from_open():
    customer = Customer(id=uuid4(), email="a@example.com", name="Ada")
    order = Order(id=uuid4(), status=OrderStatus.OPEN, items=[], customer=customer)
    mock_db = _mock_db_with_order(order)

    result = OrderService.cancel(mock_db, order.id, CURRENT_USER)

    assert result.status == OrderStatus.CANCELED


def test_search_eager_loads_items_to_avoid_n_plus_one():
    mock_db = MagicMock(spec=Session)
    mock_filtered_query = mock_db.query.return_value.filter.return_value

    with patch("api.services.order_service.paginate", return_value=([], 0)) as mock_paginate:
        OrderService.search(mock_db, SearchRequest())

    mock_filtered_query.options.assert_called_once()
    (loader_option,) = mock_filtered_query.options.call_args[0]
    assert str(loader_option) == str(selectinload(Order.items))
    mock_paginate.assert_called_once_with(mock_filtered_query.options.return_value, Order, SearchRequest())
