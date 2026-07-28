import enum

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

# UUID gerado pelo banco (ver "Convenções de model" na skill fastapi-feature): nunca
# default=uuid.uuid4 em Python, deixa o SQLAlchemy reler o valor gerado pelo Postgres.
_GEN_RANDOM_UUID = text("gen_random_uuid()")


class AuditMixin:
    """Timestamp + ator de toda criação/atualização. O ator é sempre atribuído
    explicitamente pelo service a partir do current_user — nunca por server_default."""

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    created_by = Column(String, nullable=False)
    updated_by = Column(String, nullable=False)


class SoftDeleteMixin:
    """deleted_at nulo = registro ativo. Toda query de leitura do service precisa
    filtrar `.filter(Model.deleted_at.is_(None))` manualmente — SQLAlchemy não aplica
    esse filtro sozinho."""

    deleted_at = Column(DateTime(timezone=True), nullable=True)
    deleted_by = Column(String, nullable=True)


class OrderStatus(enum.StrEnum):
    OPEN = "OPEN"
    CONFIRMED = "CONFIRMED"
    CANCELED = "CANCELED"


class Customer(Base, AuditMixin, SoftDeleteMixin):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("tax_id", name="uq_customers_tax_id"),
        UniqueConstraint("passport_number", name="uq_customers_passport_number"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=_GEN_RANDOM_UUID)
    name = Column(String, nullable=False)
    tax_id = Column(String, nullable=False, info={"sensitive": True})
    passport_number = Column(String, nullable=True, info={"sensitive": True})
    email = Column(String, nullable=False, info={"sensitive": True})

    orders = relationship("Order", back_populates="customer")


class Order(Base, AuditMixin, SoftDeleteMixin):
    __tablename__ = "orders"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=_GEN_RANDOM_UUID)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False)
    status = Column(Enum(OrderStatus, name="order_status"), nullable=False, default=OrderStatus.OPEN)
    version = Column(Integer, nullable=False, default=1)

    # Lock otimista: o SQLAlchemy incrementa/checa `version` a cada UPDATE/commit e lança
    # StaleDataError se a linha mudou desde a leitura — tratado globalmente em main.py.
    __mapper_args__ = {"version_id_col": version}

    customer = relationship("Customer", back_populates="orders")
    # cascade: Item é entidade-filha do agregado Order, sem existência própria fora dele.
    items = relationship("Item", back_populates="order", cascade="all, delete-orphan")

    @hybrid_property
    def total(self):
        return sum(item.unit_price * item.quantity for item in self.items) if self.items else 0

    @property
    def is_editable(self) -> bool:
        return self.status == OrderStatus.OPEN


class Item(Base):
    __tablename__ = "items"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=_GEN_RANDOM_UUID)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False)
    description = Column(String(255), nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)
    quantity = Column(Integer, nullable=False)

    order = relationship("Order", back_populates="items")

    @hybrid_property
    def subtotal(self):
        return self.unit_price * self.quantity
