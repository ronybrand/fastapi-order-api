from api.models.models import Customer


def _index(name: str):
    return next(index for index in Customer.__table__.indexes if index.name == name)


def test_tax_id_is_unique_only_among_active_customers():
    index = _index("uq_customers_tax_id")

    assert index.unique
    assert [column.name for column in index.columns] == ["tax_id"]
    assert str(index.dialect_options["postgresql"]["where"]) == "deleted_at IS NULL"


def test_passport_number_is_unique_only_among_active_customers():
    index = _index("uq_customers_passport_number")

    assert index.unique
    assert [column.name for column in index.columns] == ["passport_number"]
    assert str(index.dialect_options["postgresql"]["where"]) == "deleted_at IS NULL"


def test_no_full_table_unique_constraint_is_left_on_the_documents():
    """A plain UniqueConstraint would keep a soft-deleted customer's tax_id reserved forever and
    turn re-registering it into an unhandled IntegrityError (500)."""
    from sqlalchemy import UniqueConstraint

    constraints = [c for c in Customer.__table__.constraints if isinstance(c, UniqueConstraint)]

    assert constraints == []
