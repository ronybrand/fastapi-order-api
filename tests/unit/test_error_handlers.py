import asyncio
import json
from unittest.mock import Mock

from fastapi.exceptions import RequestValidationError
from slowapi.errors import RateLimitExceeded
from sqlalchemy.orm.exc import StaleDataError

from api.security.middleware import _request_id_ctx
from api.utils.custom_api_exception import CustomAPIException
from main import (
    custom_api_exception_handler,
    rate_limit_exceeded_handler,
    stale_data_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)


def _run(coro):
    return asyncio.run(coro)


def _fake_request():
    request = Mock()
    request.url.path = "/orders/123"
    request.method = "GET"
    return request


def test_custom_api_exception_includes_request_id_in_body():
    token = _request_id_ctx.set("req-abc-123")
    try:
        exc = CustomAPIException(
            status_code=404, message="Order not found", code="NOT_FOUND-00", params={"id": "123"}
        )
        response = _run(custom_api_exception_handler(_fake_request(), exc))
    finally:
        _request_id_ctx.reset(token)

    body = json.loads(response.body)
    assert body["request_id"] == "req-abc-123"
    assert body["message"] == "Order not found"
    assert body["code"] == "NOT_FOUND-00"
    assert body["params"] == {"id": "123"}


def test_stale_data_exception_includes_request_id_in_body():
    token = _request_id_ctx.set("req-conflict-1")
    try:
        response = _run(stale_data_exception_handler(_fake_request(), StaleDataError("Order", 1)))
    finally:
        _request_id_ctx.reset(token)

    body = json.loads(response.body)
    assert body["request_id"] == "req-conflict-1"
    assert body["code"] == "CONFLICT-00"


def test_unhandled_exception_includes_request_id_without_leaking_details():
    token = _request_id_ctx.set("req-internal-1")
    try:
        response = _run(unhandled_exception_handler(_fake_request(), ValueError("boom, secret detail")))
    finally:
        _request_id_ctx.reset(token)

    body = json.loads(response.body)
    assert body["request_id"] == "req-internal-1"
    assert body["code"] == "INTERNAL-00"
    assert "boom" not in body["message"]


def test_validation_exception_includes_request_id_in_body():
    token = _request_id_ctx.set("req-validation-1")
    try:
        errors = [{"loc": ("body", "name"), "msg": "field required", "type": "missing"}]
        response = _run(validation_exception_handler(_fake_request(), RequestValidationError(errors)))
    finally:
        _request_id_ctx.reset(token)

    body = json.loads(response.body)
    assert body["request_id"] == "req-validation-1"
    assert body["code"] == "VALIDATION-01"


def test_rate_limit_exceeded_uses_the_app_error_shape_with_request_id():
    fake_limit = Mock(error_message=None, limit="100 per 1 minute")
    exc = RateLimitExceeded(fake_limit)

    token = _request_id_ctx.set("req-rate-1")
    try:
        response = _run(rate_limit_exceeded_handler(_fake_request(), exc))
    finally:
        _request_id_ctx.reset(token)

    assert response.status_code == 429
    body = json.loads(response.body)
    assert body["request_id"] == "req-rate-1"
    assert body["code"] == "RATE-00"
    assert "100 per 1 minute" in body["params"]["detail"]


def test_request_id_defaults_to_placeholder_outside_a_request_context():
    # Fora do middleware (nenhum request-id setado), o contextvar cai no
    # default "-" - mesmo valor ja usado pelos logs (RequestIdFilter).
    exc = CustomAPIException(status_code=400, message="bad", code="VALIDATION-00", params={})
    response = _run(custom_api_exception_handler(_fake_request(), exc))

    body = json.loads(response.body)
    assert body["request_id"] == "-"
