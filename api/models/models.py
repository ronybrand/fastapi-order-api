import enum

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import declarative_base, relationship

from api.utils.field_limits import MAX_EMAIL_LENGTH, MAX_NAME_LENGTH

Base = declarative_base()

# UUID gerado pelo banco (ver "Convenções de model" na skill fastapi-feature): nunca
# default=uuid.uuid4 em Python, deixa o SQLAlchemy reler o valor gerado pelo Postgres.
_GEN_RANDOM_UUID = text("gen_random_uuid()")

# `sub` do token (quem fez a mutacao). O limite de 200 e conferido em get_current_user.
_ACTOR_LENGTH = 200


class AuditMixin:
    """Timestamp + ator de toda criação/atualização. O ator é sempre atribuído
    explicitamente pelo service a partir do current_user — nunca por server_default."""

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    created_by = Column(String(_ACTOR_LENGTH), nullable=False)
    updated_by = Column(String(_ACTOR_LENGTH), nullable=False)


class SoftDeleteMixin:
    """deleted_at nulo = registro ativo. Toda query de leitura do service precisa
    filtrar `.filter(Model.deleted_at.is_(None))` manualmente — SQLAlchemy não aplica
    esse filtro sozinho."""

    deleted_at = Column(DateTime(timezone=True), nullable=True)
    deleted_by = Column(String(_ACTOR_LENGTH), nullable=True)


class OrderStatus(enum.StrEnum):
    OPEN = "OPEN"
    CONFIRMED = "CONFIRMED"
    CANCELED = "CANCELED"


class Customer(Base, AuditMixin, SoftDeleteMixin):
    __tablename__ = "customers"
    # Unique among active customers only: a soft-deleted customer releases its tax_id/passport_number.
    # (A plain UniqueConstraint keeps them reserved forever, and the service-level check only looks at
    # active rows - so re-registering a deleted document passed the check and failed on INSERT as a 500.)
    __table_args__ = (
        Index("uq_customers_tax_id", "tax_id", unique=True, postgresql_where=text("deleted_at IS NULL")),
        Index(
            "uq_customers_passport_number",
            "passport_number",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=_GEN_RANDOM_UUID)
    # Tamanhos iguais aos limites dos schemas (api/utils/field_limits.py): o banco recusa o que o schema
    # recusaria.
    name = Column(String(MAX_NAME_LENGTH), nullable=False)
    tax_id = Column(String(20), nullable=False, info={"sensitive": True})
    passport_number = Column(String(9), nullable=True, info={"sensitive": True})
    email = Column(String(MAX_EMAIL_LENGTH), nullable=False, info={"sensitive": True})
    version = Column(Integer, nullable=False, default=1)

    # Lock otimista (como Order): dois PUT concorrentes no mesmo cliente deixam de sobrescrever um ao outro
    # em silencio - o segundo recebe StaleDataError, tratado globalmente como 409 em main.py.
    __mapper_args__ = {"version_id_col": version}

    orders = relationship("Order", back_populates="customer")


class Order(Base, AuditMixin, SoftDeleteMixin):
    __tablename__ = "orders"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=_GEN_RANDOM_UUID)
    customer_id = Column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
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
    # Defesa em profundidade: o schema ja recusa, mas qualquer outro caminho de escrita (script, migration de
    # dados, outro servico) tambem nao consegue gravar item com quantidade ou preco nao positivos.
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_items_quantity_positive"),
        CheckConstraint("unit_price > 0", name="ck_items_unit_price_positive"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=_GEN_RANDOM_UUID)
    order_id = Column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    description = Column(String(255), nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)
    quantity = Column(Integer, nullable=False)

    order = relationship("Order", back_populates="items")

    @hybrid_property
    def subtotal(self):
        return self.unit_price * self.quantity
