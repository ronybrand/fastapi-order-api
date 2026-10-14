from datetime import datetime

import pytest
from sqlalchemy import Boolean, Column, DateTime, Integer, String, create_engine
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
    secret = Column(String, nullable=True, info={"sensitive": True})
    active = Column(Boolean, nullable=True)
    created = Column(DateTime, nullable=True)


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


def test_filter_on_sensitive_field_is_ignored_so_it_cannot_be_used_as_an_oracle(db_session):
    db_session.add_all(
        [_Widget(score=1, name="a", secret="alpha"), _Widget(score=2, name="b", secret="beta")]
    )
    db_session.commit()

    request = SearchRequest(filters={"secret": [{"op": "eq", "value": "alpha"}]})
    _items, total = paginate(db_session.query(_Widget), _Widget, request)

    assert total == 2


def test_sort_on_sensitive_field_is_rejected_as_unknown(db_session):
    request = SearchRequest(sort="secret")

    with pytest.raises(CustomAPIException) as exc:
        paginate(db_session.query(_Widget), _Widget, request)

    assert exc.value.detail["code"] == "VALIDATION-06"


def test_like_treats_percent_and_underscore_literally(db_session):
    for score, name in enumerate(["100%", "100x", "a_c", "abc"]):
        db_session.add(_Widget(score=score, name=name))
    db_session.commit()

    def like(term):
        request = SearchRequest(filters={"name": [{"op": "lk", "value": term}]})
        return paginate(db_session.query(_Widget), _Widget, request)

    percent = like("0%")
    underscore = like("a_c")

    assert [w.name for w in percent[0]] == ["100%"]
    assert [w.name for w in underscore[0]] == ["a_c"]


def test_filter_on_unknown_field_is_silently_ignored(db_session):
    _make_widget(db_session, score=1)
    _make_widget(db_session, score=2)

    request = SearchRequest(filters={"not_a_real_column": [{"op": "eq", "value": "x"}]})
    items, total = paginate(db_session.query(_Widget), _Widget, request)

    assert total == 2


def test_sort_on_unknown_field_raises_validation_error(db_session):
    request = SearchRequest(sort="not_a_real_column")

    with pytest.raises(CustomAPIException) as exc:
        paginate(db_session.query(_Widget), _Widget, request)

    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "VALIDATION-06"


def test_sort_descending_orders_highest_score_first(db_session):
    _make_widget(db_session, score=1)
    highest = _make_widget(db_session, score=10)
    _make_widget(db_session, score=5)

    request = SearchRequest(sort="-score")
    items, _total = paginate(db_session.query(_Widget), _Widget, request)

    assert items[0].id == highest.id


def _search(db_session, field, op, value):
    request = SearchRequest(filters={field: [{"op": op, "value": value}]})
    return paginate(db_session.query(_Widget), _Widget, request)


def _assert_invalid_filter(db_session, field, op, value):
    with pytest.raises(CustomAPIException) as exc:
        _search(db_session, field, op, value)

    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "VALIDATION-05"


def test_boolean_filter_understands_false(db_session):
    db_session.add_all([_Widget(score=1, name="on", active=True), _Widget(score=2, name="off", active=False)])
    db_session.commit()

    items, total = _search(db_session, "active", "eq", "false")

    assert [w.name for w in items] == ["off"]
    assert total == 1


def test_boolean_filter_accepts_json_booleans(db_session):
    db_session.add_all([_Widget(score=1, name="on", active=True), _Widget(score=2, name="off", active=False)])
    db_session.commit()

    items, _total = _search(db_session, "active", "eq", True)

    assert [w.name for w in items] == ["on"]


def test_boolean_filter_rejects_anything_that_is_not_true_or_false(db_session):
    _assert_invalid_filter(db_session, "active", "eq", "maybe")


def test_datetime_filter_parses_iso_8601(db_session):
    db_session.add_all(
        [
            _Widget(score=1, name="old", created=datetime(2025, 1, 1)),
            _Widget(score=2, name="new", created=datetime(2026, 1, 1)),
        ]
    )
    db_session.commit()

    items, _total = _search(db_session, "created", "gte", "2025-06-01T00:00:00")

    assert [w.name for w in items] == ["new"]


def test_datetime_filter_rejects_garbage(db_session):
    _assert_invalid_filter(db_session, "created", "eq", "yesterday")


def test_integer_filter_rejects_a_fractional_number(db_session):
    _assert_invalid_filter(db_session, "score", "eq", 1.5)


def test_integer_filter_rejects_a_boolean(db_session):
    _assert_invalid_filter(db_session, "score", "eq", True)


def test_between_requires_exactly_two_values(db_session):
    _assert_invalid_filter(db_session, "score", "between", [1])
    _assert_invalid_filter(db_session, "score", "between", [1, 2, 3])
    _assert_invalid_filter(db_session, "score", "between", 1)


def test_between_with_two_values_filters_inclusively(db_session):
    for score in (1, 5, 9):
        _make_widget(db_session, score=score)

    items, _total = _search(db_session, "score", "between", [1, 5])

    assert sorted(w.score for w in items) == [1, 5]


def test_like_is_only_allowed_on_text_columns(db_session):
    _assert_invalid_filter(db_session, "score", "lk", "1")


def test_a_list_is_only_allowed_for_in_and_between(db_session):
    _assert_invalid_filter(db_session, "score", "eq", [1, 2])


def test_null_value_is_rejected(db_session):
    _assert_invalid_filter(db_session, "score", "eq", None)
