import pytest
from pydantic import ValidationError

from api.schemas.schemas import SearchRequest
from api.utils.search_limits import (
    MAX_CONDITIONS_PER_FIELD,
    MAX_FILTER_FIELDS,
    MAX_IN_VALUES,
    MAX_VALUE_LENGTH,
)


def _filters(field_count=1, conditions=1, value="x", op="eq"):
    return {f"field{n}": [{"op": op, "value": value}] * conditions for n in range(field_count)}


def test_filters_at_every_limit_are_accepted():
    request = SearchRequest(
        filters=_filters(MAX_FILTER_FIELDS, MAX_CONDITIONS_PER_FIELD, "x" * MAX_VALUE_LENGTH)
    )

    assert len(request.filters) == MAX_FILTER_FIELDS


def test_too_many_filter_fields_is_rejected():
    with pytest.raises(ValidationError):
        SearchRequest(filters=_filters(field_count=MAX_FILTER_FIELDS + 1))


def test_too_many_conditions_on_one_field_is_rejected():
    with pytest.raises(ValidationError):
        SearchRequest(filters=_filters(conditions=MAX_CONDITIONS_PER_FIELD + 1))


def test_in_list_above_limit_is_rejected():
    with pytest.raises(ValidationError):
        SearchRequest(filters=_filters(op="in", value=list(range(MAX_IN_VALUES + 1))))


def test_in_list_at_limit_is_accepted():
    SearchRequest(filters=_filters(op="in", value=list(range(MAX_IN_VALUES))))


def test_value_longer_than_limit_is_rejected():
    with pytest.raises(ValidationError):
        SearchRequest(filters=_filters(value="x" * (MAX_VALUE_LENGTH + 1)))


def test_long_string_inside_a_list_is_rejected():
    with pytest.raises(ValidationError):
        SearchRequest(filters=_filters(op="in", value=["ok", "x" * (MAX_VALUE_LENGTH + 1)]))


def test_offset_that_overflows_a_32_bit_integer_is_rejected():
    with pytest.raises(ValidationError):
        SearchRequest(page=2_147_483_647, size=100)


def test_largest_offset_that_fits_is_accepted():
    SearchRequest(page=21_474_836, size=100)
