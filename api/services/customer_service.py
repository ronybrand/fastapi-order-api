import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from api.dependencies.dependencies import CurrentUser
from api.models.models import Customer, Order
from api.schemas.schemas import CustomerInput, SearchRequest
from api.utils.custom_api_exception import CustomAPIException
from api.utils.pagination import paginate

logger = logging.getLogger(__name__)


def _active_customer_query(db: Session):
    return db.query(Customer).filter(Customer.deleted_at.is_(None))


def _assert_unique(db: Session, customer: CustomerInput, exclude_id: UUID | None = None) -> None:
    tax_id_query = _active_customer_query(db).filter(Customer.tax_id == customer.tax_id)
    if exclude_id is not None:
        tax_id_query = tax_id_query.filter(Customer.id != exclude_id)
    if tax_id_query.first() is not None:
        raise CustomAPIException(
            status_code=409,
            message=f"Customer with tax_id {customer.tax_id} already exists",
            code="CONFLICT-01",
            params={"tax_id": customer.tax_id},
        )

    if customer.passport_number:
        passport_query = _active_customer_query(db).filter(
            Customer.passport_number == customer.passport_number
        )
        if exclude_id is not None:
            passport_query = passport_query.filter(Customer.id != exclude_id)
        if passport_query.first() is not None:
            raise CustomAPIException(
                status_code=409,
                message=f"Customer with passport_number {customer.passport_number} already exists",
                code="CONFLICT-02",
                params={"passport_number": customer.passport_number},
            )


class CustomerService:
    @staticmethod
    def create(db: Session, customer: CustomerInput, current_user: CurrentUser) -> Customer:
        _assert_unique(db, customer)

        db_customer = Customer(
            name=customer.name,
            tax_id=customer.tax_id,
            passport_number=customer.passport_number,
            email=customer.email,
            created_by=current_user.id,
            updated_by=current_user.id,
        )
        db.add(db_customer)
        db.commit()
        db.refresh(db_customer)
        logger.info("customer_created: id=%s created_by=%s", db_customer.id, current_user.id)
        return db_customer

    @staticmethod
    def get(db: Session, customer_id: UUID) -> Customer:
        customer = _active_customer_query(db).filter(Customer.id == customer_id).first()
        if customer is None:
            raise CustomAPIException(
                status_code=404,
                message=f"Customer {customer_id} not found",
                code="RESOURCE-NOT-FOUND-01",
                params={"id": str(customer_id)},
            )
        return customer

    @staticmethod
    def update(
        db: Session, customer_id: UUID, customer: CustomerInput, current_user: CurrentUser
    ) -> Customer:
        db_customer = CustomerService.get(db, customer_id)
        _assert_unique(db, customer, exclude_id=customer_id)

        db_customer.name = customer.name
        db_customer.tax_id = customer.tax_id
        db_customer.passport_number = customer.passport_number
        db_customer.email = customer.email
        db_customer.updated_by = current_user.id

        db.commit()
        db.refresh(db_customer)
        logger.info("customer_updated: id=%s updated_by=%s", db_customer.id, current_user.id)
        return db_customer

    @staticmethod
    def delete(db: Session, customer_id: UUID, current_user: CurrentUser) -> None:
        db_customer = CustomerService.get(db, customer_id)

        has_orders = (
            db.query(Order)
            .filter(Order.customer_id == customer_id, Order.deleted_at.is_(None))
            .count()
        )
        if has_orders > 0:
            raise CustomAPIException(
                status_code=409,
                message=f"Customer {customer_id} has orders and cannot be deleted",
                code="CONFLICT-03",
                params={"id": str(customer_id)},
            )

        db_customer.deleted_at = datetime.now(UTC)
        db_customer.deleted_by = current_user.id
        db.commit()
        logger.info("customer_deleted: id=%s deleted_by=%s", customer_id, current_user.id)

    @staticmethod
    def search(db: Session, request: SearchRequest) -> tuple[list[Customer], int]:
        return paginate(_active_customer_query(db), Customer, request)
