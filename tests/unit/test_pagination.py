import pytest
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from api.schemas.schemas import SearchRequest
from api.utils.custom_api_exception import CustomAPIException
from api.utils.pagination import paginate

_Base = declarative_base()


class _Widget(_Base):
    __tablename__ = "widgets"

    id = Column(Integer, primary_key=True)
    score = Column(Integer, nullable=False)
    name = Column(String, nullable=False)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    _Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _make_widget(db_session, score: int, name: str = "w") -> _Widget:
    widget = _Widget(score=score, name=name)
    db_session.add(widget)
    db_session.commit()
    return widget


def test_filter_with_multiple_conditions_on_same_field_applies_and(db_session):
    _make_widget(db_session, score=1)
    middle = _make_widget(db_session, score=5)
    _make_widget(db_session, score=10)

    request = SearchRequest(filters={"score": [{"op": "gte", "value": 3}, {"op": "lte", "value": 7}]})
    items, total = paginate(db_session.query(_Widget), _Widget, request)

    assert total == 1
    assert items[0].id == middle.id


def test_filter_with_single_condition_still_works(db_session):
    _make_widget(db_session, score=1)
    match = _make_widget(db_session, score=5)

    request = SearchRequest(filters={"score": [{"op": "eq", "value": 5}]})
    items, total = paginate(db_session.query(_Widget), _Widget, request)

    assert total == 1
    assert items[0].id == match.id


def test_filter_with_in_operator_and_list_values(db_session):
    a = _make_widget(db_session, score=1)
    _make_widget(db_session, score=2)
    c = _make_widget(db_session, score=3)

    request = SearchRequest(filters={"score": [{"op": "in", "value": [1, 3]}]})
    items, total = paginate(db_session.query(_Widget), _Widget, request)

    assert total == 2
    assert {item.id for item in items} == {a.id, c.id}


def test_filter_with_in_operator_and_string_values_for_int_column_coerces_elements(db_session):
    a = _make_widget(db_session, score=1)
    _make_widget(db_session, score=2)
    c = _make_widget(db_session, score=3)

    request = SearchRequest(filters={"score": [{"op": "in", "value": ["1", "3"]}]})
    items, total = paginate(db_session.query(_Widget), _Widget, request)

    assert total == 2
    assert {item.id for item in items} == {a.id, c.id}


def test_filter_with_in_operator_and_invalid_list_value_raises_validation_error(db_session):
    request = SearchRequest(filters={"score": [{"op": "in", "value": ["not-a-number"]}]})

    with pytest.raises(CustomAPIException) as exc:
        paginate(db_session.query(_Widget), _Widget, request)

    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "VALIDATION-05"
