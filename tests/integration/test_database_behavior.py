"""Comportamentos que so existem contra um Postgres de verdade, com commits reais e conexoes concorrentes:
unicidade parcial, corrida entre excluir cliente e criar pedido, lock otimista e o ciclo das migrations.

Cada teste roda num banco proprio (criado e descartado aqui) porque faz commit de verdade: o isolamento por
transacao+rollback do conftest nao serve para duas sessoes concorrentes."""

import os
import subprocess
import sys
import threading
import uuid

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from api.dependencies.dependencies import CurrentUser
from api.models.models import Base, Customer, Order
from api.schemas.schemas import CustomerInput, ItemInput, OrderCreate
from api.services.customer_service import CustomerService
from api.services.order_service import OrderService
from api.utils.custom_api_exception import CustomAPIException

ADMIN = CurrentUser(id="admin-1", roles=["admin"])
USER = CurrentUser(id="user-1", roles=["user"])


def _customer_input(**overrides) -> CustomerInput:
    payload = {"name": "Ada", "tax_id": "AB123456", "passport_number": None, "email": "ada@example.com"}
    payload.update(overrides)
    return CustomerInput(**payload)


@pytest.fixture
def database_url(postgres_container):
    """URL de um banco novo e vazio, descartado no fim do teste."""
    admin_url = postgres_container.get_connection_url().replace("localhost", "127.0.0.1")
    name = f"t_{uuid.uuid4().hex}"
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    yield make_url(admin_url).set(database=name).render_as_string(hide_password=False)
    with admin_engine.connect() as connection:
        connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
    admin_engine.dispose()


@pytest.fixture
def fresh_engine(database_url):
    engine = create_engine(database_url)
    with engine.connect() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        connection.commit()
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


def _in_threads(*callables):
    """Roda as funcoes ao mesmo tempo (largam juntas numa barreira).

    Devolve ("ok", valor) ou ("error", excecao) por funcao."""
    barrier = threading.Barrier(len(callables))
    results: list = [None] * len(callables)

    def run(index, function):
        barrier.wait()
        try:
            results[index] = ("ok", function())
        except Exception as error:  # noqa: BLE001 - o teste inspeciona qualquer falha
            results[index] = ("error", error)

    threads = [threading.Thread(target=run, args=(i, f)) for i, f in enumerate(callables)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results


def _count(engine, sql: str, **params) -> int:
    with engine.connect() as connection:
        return connection.execute(text(sql), params).scalar_one()


# --- unicidade parcial -----------------------------------------------------------------------------------
def test_a_deleted_customers_tax_id_can_be_registered_again(fresh_engine):
    with Session(fresh_engine) as db:
        created_id = CustomerService.create(db, _customer_input(), ADMIN).id
        CustomerService.delete(db, created_id, ADMIN)
        # Antes: o UNIQUE cheio ainda reservava o documento e isto estourava como IntegrityError (500).
        again_id = CustomerService.create(db, _customer_input(), ADMIN).id

    assert again_id != created_id
    assert _count(fresh_engine, "SELECT count(*) FROM customers WHERE tax_id = 'AB123456'") == 2
    active = "SELECT count(*) FROM customers WHERE tax_id = 'AB123456' AND deleted_at IS NULL"
    assert _count(fresh_engine, active) == 1


def test_two_simultaneous_registrations_of_the_same_document_leave_exactly_one(fresh_engine):
    def register():
        with Session(fresh_engine) as db:
            return CustomerService.create(db, _customer_input(), ADMIN)

    results = _in_threads(register, register)

    assert [kind for kind, _ in results].count("ok") == 1
    (failure,) = [value for kind, value in results if kind == "error"]
    # O service-level check devolve 409; se os dois passarem por ele juntos, quem barra e o indice unico.
    assert isinstance(failure, CustomAPIException | IntegrityError)
    assert _count(fresh_engine, "SELECT count(*) FROM customers WHERE deleted_at IS NULL") == 1


# --- corrida entre excluir cliente e criar pedido ----------------------------------------------------------
def test_deleting_a_customer_and_creating_an_order_never_leave_an_active_order_under_a_deleted_customer(
    fresh_engine,
):
    item = ItemInput(description="Widget", unit_price=1, quantity=1)

    for attempt in range(10):
        with Session(fresh_engine) as db:
            customer = CustomerService.create(
                db, _customer_input(tax_id=f"RACE{attempt:04d}", email=f"race{attempt}@example.com"), ADMIN
            )
        customer_id = customer.id

        def create_order(customer_id=customer_id):
            with Session(fresh_engine) as db:
                return OrderService.create(db, OrderCreate(customer_id=customer_id, items=[item]), USER)

        def delete_customer(customer_id=customer_id):
            with Session(fresh_engine) as db:
                return CustomerService.delete(db, customer_id, ADMIN)

        order_result, delete_result = _in_threads(create_order, delete_customer)

        # Uma das duas tem que ter perdido; as falhas aceitaveis sao as de negocio (409/400).
        for kind, value in (order_result, delete_result):
            if kind == "error":
                assert isinstance(value, CustomAPIException), value
        assert not (order_result[0] == "ok" and delete_result[0] == "ok"), f"attempt {attempt}"
        assert (
            _count(
                fresh_engine,
                "SELECT count(*) FROM orders o JOIN customers c ON c.id = o.customer_id "
                "WHERE o.deleted_at IS NULL AND c.deleted_at IS NOT NULL",
            )
            == 0
        )


# --- lock otimista -----------------------------------------------------------------------------------------
def test_two_concurrent_updates_of_the_same_customer_do_not_silently_overwrite_each_other(fresh_engine):
    with Session(fresh_engine) as db:
        customer_id = CustomerService.create(db, _customer_input(), ADMIN).id

    with Session(fresh_engine) as first, Session(fresh_engine) as second:
        loaded_by_first = first.get(Customer, customer_id)
        loaded_by_second = second.get(Customer, customer_id)

        loaded_by_first.name = "First writer"
        first.commit()

        loaded_by_second.name = "Second writer"
        with pytest.raises(StaleDataError):
            second.commit()

    with Session(fresh_engine) as db:
        assert db.get(Customer, customer_id).name == "First writer"


def test_the_database_itself_refuses_an_item_with_a_non_positive_quantity_or_price(fresh_engine):
    with Session(fresh_engine) as db:
        customer_id = CustomerService.create(db, _customer_input(), ADMIN).id
        order_id = OrderService.create(db, OrderCreate(customer_id=customer_id, items=[]), USER).id

    for quantity, price in ((0, "1.00"), (-1, "1.00"), (1, "0.00"), (1, "-5.00")):
        with fresh_engine.connect() as connection:
            with pytest.raises(IntegrityError):
                connection.execute(
                    text(
                        "INSERT INTO items (order_id, description, unit_price, quantity) "
                        "VALUES (:order_id, 'x', :price, :quantity)"
                    ),
                    {"order_id": order_id, "price": price, "quantity": quantity},
                )


def test_two_concurrent_changes_to_the_same_order_conflict(fresh_engine):
    with Session(fresh_engine) as db:
        customer_id = CustomerService.create(db, _customer_input(), ADMIN).id
        order_id = OrderService.create(db, OrderCreate(customer_id=customer_id, items=[]), USER).id

    with Session(fresh_engine) as first, Session(fresh_engine) as second:
        loaded_by_first = first.get(Order, order_id)
        loaded_by_second = second.get(Order, order_id)
        loaded_by_first.updated_by = "first"
        first.commit()
        loaded_by_second.updated_by = "second"
        with pytest.raises(StaleDataError):
            second.commit()


# --- migrations --------------------------------------------------------------------------------------------
def _alembic(database_url: str, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": database_url}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args], env=env, capture_output=True, text=True, check=False
    )


def test_migrations_apply_roll_back_and_apply_again_leaving_model_and_schema_in_agreement(database_url):
    upgraded = _alembic(database_url, "upgrade", "head")
    assert upgraded.returncode == 0, upgraded.stderr

    # O que as migrations constroem tem que ser exatamente o que os models declaram.
    checked = _alembic(database_url, "check")
    assert checked.returncode == 0, checked.stdout + checked.stderr

    engine = create_engine(database_url)
    try:
        inspector = inspect(engine)
        indexes = {index["name"]: index for index in inspector.get_indexes("customers")}
        assert indexes["uq_customers_tax_id"]["unique"]
        assert "deleted_at IS NULL" in indexes["uq_customers_tax_id"]["dialect_options"]["postgresql_where"]
        assert indexes["uq_customers_passport_number"]["unique"]
        columns = {column["name"]: column for column in inspector.get_columns("customers")}
        assert columns["name"]["type"].length == 200
        assert "version" in columns
        checks = {check["name"] for check in inspector.get_check_constraints("items")}
        assert {"ck_items_quantity_positive", "ck_items_unit_price_positive"} <= checks
    finally:
        engine.dispose()

    rolled_back = _alembic(database_url, "downgrade", "base")
    assert rolled_back.returncode == 0, rolled_back.stderr

    again = _alembic(database_url, "upgrade", "head")
    assert again.returncode == 0, again.stderr
