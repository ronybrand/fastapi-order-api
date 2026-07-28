import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from api.dependencies.dependencies import CurrentUser
from api.events.order_events import build_order_status_changed_event, publish_order_status_changed
from api.models.models import Customer, Item, Order, OrderStatus
from api.schemas.schemas import ItemInput, OrderCreate, SearchRequest
from api.utils.custom_api_exception import CustomAPIException
from api.utils.pagination import paginate

logger = logging.getLogger(__name__)


def _active_order_query(db: Session):
    return db.query(Order).filter(Order.deleted_at.is_(None))


def _get_active_order(db: Session, order_id: UUID) -> Order:
    order = _active_order_query(db).filter(Order.id == order_id).first()
    if order is None:
        raise CustomAPIException(
            status_code=404,
            message=f"Order {order_id} not found",
            code="RESOURCE-NOT-FOUND-02",
            params={"id": str(order_id)},
        )
    return order


def _assert_editable(order: Order) -> None:
    if not order.is_editable:
        raise CustomAPIException(
            status_code=400,
            message=f"Order {order.id} is not editable in status {order.status.value}",
            code="VALIDATION-02",
            params={"id": str(order.id), "status": order.status.value},
        )


def _get_item(order: Order, item_id: UUID) -> Item:
    for item in order.items:
        if item.id == item_id:
            return item
    raise CustomAPIException(
        status_code=404,
        message=f"Item {item_id} not found in order {order.id}",
        code="RESOURCE-NOT-FOUND-03",
        params={"order_id": str(order.id), "item_id": str(item_id)},
    )


def _touch(order: Order, current_user: CurrentUser) -> None:
    """Força um UPDATE na linha do Order mesmo quando só um filho (Item) mudou, para que o
    lock otimista (`version_id_col`) também cubra mutações de item — ver skill
    fastapi-feature, "Contador mutável referenciado por um agregado relacionado"."""
    order.updated_by = current_user.id


class OrderService:
    @staticmethod
    def create(db: Session, order_in: OrderCreate, current_user: CurrentUser) -> Order:
        customer = (
            db.query(Customer)
            .filter(Customer.id == order_in.customer_id, Customer.deleted_at.is_(None))
            .first()
        )
        if customer is None:
            raise CustomAPIException(
                status_code=400,
                message=f"Customer {order_in.customer_id} not found",
                code="VALIDATION-07",
                params={"customer_id": str(order_in.customer_id)},
            )

        db_order = Order(
            customer_id=customer.id,
            status=OrderStatus.OPEN,
            created_by=current_user.id,
            updated_by=current_user.id,
        )
        db.add(db_order)
        db.flush()  # atribui db_order.id sem commitar

        for item in order_in.items:
            db.add(
                Item(
                    order_id=db_order.id,
                    description=item.description,
                    unit_price=item.unit_price,
                    quantity=item.quantity,
                )
            )

        db.commit()
        db.refresh(db_order)
        logger.info(
            "order_created: id=%s customer_id=%s created_by=%s", db_order.id, customer.id, current_user.id
        )
        return db_order

    @staticmethod
    def get(db: Session, order_id: UUID) -> Order:
        return _get_active_order(db, order_id)

    @staticmethod
    def delete(db: Session, order_id: UUID, current_user: CurrentUser) -> None:
        order = _get_active_order(db, order_id)
        order.deleted_at = datetime.now(UTC)
        order.deleted_by = current_user.id
        db.commit()
        logger.info("order_deleted: id=%s deleted_by=%s", order_id, current_user.id)

    @staticmethod
    def add_item(db: Session, order_id: UUID, item_in: ItemInput, current_user: CurrentUser) -> Order:
        order = _get_active_order(db, order_id)
        _assert_editable(order)

        db.add(
            Item(
                order_id=order.id,
                description=item_in.description,
                unit_price=item_in.unit_price,
                quantity=item_in.quantity,
            )
        )
        _touch(order, current_user)
        db.commit()
        db.refresh(order)
        return order

    @staticmethod
    def update_item_quantity(
        db: Session, order_id: UUID, item_id: UUID, quantity: int, current_user: CurrentUser
    ) -> Order:
        order = _get_active_order(db, order_id)
        _assert_editable(order)
        item = _get_item(order, item_id)

        item.quantity = quantity
        _touch(order, current_user)
        db.commit()
        db.refresh(order)
        return order

    @staticmethod
    def remove_item(db: Session, order_id: UUID, item_id: UUID, current_user: CurrentUser) -> Order:
        order = _get_active_order(db, order_id)
        _assert_editable(order)
        item = _get_item(order, item_id)

        order.items.remove(item)
        _touch(order, current_user)
        db.commit()
        db.refresh(order)
        return order

    @staticmethod
    def confirm(db: Session, order_id: UUID, current_user: CurrentUser) -> Order:
        order = _get_active_order(db, order_id)
        if order.status != OrderStatus.OPEN:
            raise CustomAPIException(
                status_code=400,
                message=f"Cannot confirm order {order_id} from status {order.status.value}",
                code="VALIDATION-04",
                params={"id": str(order_id), "status": order.status.value},
            )
        if not order.items:
            raise CustomAPIException(
                status_code=400,
                message=f"Order {order_id} has no items and cannot be confirmed",
                code="VALIDATION-03",
                params={"id": str(order_id)},
            )

        old_status = order.status
        order.status = OrderStatus.CONFIRMED
        order.updated_by = current_user.id
        db.commit()
        db.refresh(order)
        logger.info("order_confirmed: id=%s updated_by=%s", order.id, current_user.id)

        publish_order_status_changed(build_order_status_changed_event(order, old_status))
        return order

    @staticmethod
    def cancel(db: Session, order_id: UUID, current_user: CurrentUser) -> Order:
        order = _get_active_order(db, order_id)
        if order.status == OrderStatus.CANCELED:
            raise CustomAPIException(
                status_code=400,
                message=f"Order {order_id} is already canceled",
                code="VALIDATION-04",
                params={"id": str(order_id), "status": order.status.value},
            )

        old_status = order.status
        order.status = OrderStatus.CANCELED
        order.updated_by = current_user.id
        db.commit()
        db.refresh(order)
        logger.info("order_canceled: id=%s updated_by=%s", order.id, current_user.id)

        publish_order_status_changed(build_order_status_changed_event(order, old_status))
        return order

    @staticmethod
    def search(db: Session, request: SearchRequest) -> tuple[list[Order], int]:
        return paginate(_active_order_query(db), Order, request)
