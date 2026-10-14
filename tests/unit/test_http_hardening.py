import uuid

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from api.security.middleware import (
    MAX_BODY_SIZE_BYTES,
    BodySizeLimitMiddleware,
    CorrelationIdMiddleware,
    RequestBodyTooLarge,
    SecurityHeadersMiddleware,
    request_body_too_large_handler,
)
from api.security.rate_limit import limiter, rate_limit_key
from tests.utils.auth import build_token


def _echo(request):
    return JSONResponse({"ok": True})


def _app(*middleware):
    app = Starlette(routes=[Route("/", _echo, methods=["GET", "POST"])])
    for item in reversed(middleware):  # first item ends up outermost, like in main.py
        app.add_middleware(item)
    return app


def _request(headers: dict, client=("203.0.113.9", 1234)) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": client,
    }
    return Request(scope)


# --- X-Request-Id: only a canonical UUID is propagated ---
def test_a_canonical_uuid_request_id_is_propagated():
    request_id = str(uuid.uuid4())

    response = TestClient(_app(CorrelationIdMiddleware)).get("/", headers={"X-Request-Id": request_id})

    assert response.headers["X-Request-Id"] == request_id


@pytest.mark.parametrize(
    "supplied",
    [
        "abc",
        "x" * 500,
        "not a uuid at all",
        "{" + str(uuid.uuid4()) + "}",
        str(uuid.uuid4()).replace("-", ""),
        "<script>alert(1)</script>",
        " - INFO - forged log line",
    ],
)
def test_anything_that_is_not_a_canonical_uuid_is_replaced(supplied):
    response = TestClient(_app(CorrelationIdMiddleware)).get("/", headers={"X-Request-Id": supplied})

    echoed = response.headers["X-Request-Id"]
    assert echoed != supplied
    assert str(uuid.UUID(echoed)) == echoed


def test_an_uppercase_uuid_is_normalized_to_lowercase():
    request_id = str(uuid.uuid4())

    response = TestClient(_app(CorrelationIdMiddleware)).get(
        "/", headers={"X-Request-Id": request_id.upper()}
    )

    assert response.headers["X-Request-Id"] == request_id


# --- body size limit ---
def test_oversized_declared_body_is_rejected_with_413_and_the_standard_body():
    app = _app(CorrelationIdMiddleware, SecurityHeadersMiddleware, BodySizeLimitMiddleware)

    response = TestClient(app).post(
        "/", headers={"Content-Length": str(MAX_BODY_SIZE_BYTES + 1)}, content=b"x"
    )

    body = response.json()
    assert response.status_code == 413
    assert body["message"] == "Request body too large"
    assert body["request_id"] == response.headers["X-Request-Id"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"


@pytest.mark.parametrize("declared", ["abc", "-1", "1.5", "", "10 "])
def test_a_malformed_content_length_is_a_400_not_a_500(declared):
    app = _app(CorrelationIdMiddleware, SecurityHeadersMiddleware, BodySizeLimitMiddleware)

    response = TestClient(app, raise_server_exceptions=False).get("/", headers={"Content-Length": declared})

    assert response.status_code in (400, 413)
    assert response.status_code != 500


def test_a_body_within_the_limit_passes():
    response = TestClient(_app(BodySizeLimitMiddleware)).post("/", content=b"hello")

    assert response.status_code == 200


# --- middleware order in main.py ---
def test_every_response_gets_correlation_id_and_security_headers_even_the_early_rejections():
    from main import app

    order = [middleware.cls.__name__ for middleware in app.user_middleware]

    assert order.index("CorrelationIdMiddleware") < order.index("SecurityHeadersMiddleware")
    assert order.index("SecurityHeadersMiddleware") < order.index("BodySizeLimitMiddleware")
    assert order.index("BodySizeLimitMiddleware") < order.index("SlowAPIMiddleware")


# --- rate limit partition ---
def test_authenticated_callers_are_limited_per_user_not_per_address():
    token = build_token("user-42")

    key = rate_limit_key(_request({"Authorization": f"Bearer {token}"}))

    assert key == "user:user-42"


def test_two_users_behind_the_same_address_get_separate_buckets():
    first = rate_limit_key(_request({"Authorization": f"Bearer {build_token('a')}"}))
    second = rate_limit_key(_request({"Authorization": f"Bearer {build_token('b')}"}))

    assert first != second


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer garbage"}, {"Authorization": "Basic abc"}])
def test_anonymous_or_invalid_tokens_fall_back_to_the_remote_address(headers):
    assert rate_limit_key(_request(headers)) == "203.0.113.9"


def test_health_probe_is_exempt_from_the_global_limit():
    assert "main.health_check" in limiter._exempt_routes


@pytest.mark.parametrize(
    "route",
    [
        "create_order",
        "delete_order",
        "add_item",
        "update_item_quantity",
        "remove_item",
        "confirm_order",
        "cancel_order",
    ],
)
def test_every_order_write_has_its_own_limit(route):
    assert f"api.routers.orders.{route}" in limiter._route_limits


# --- body without Content-Length (chunked) ---
async def _read_body(request):
    body = await request.body()
    return JSONResponse({"read": len(body)})


def _limited_app(limit: int):
    app = Starlette(
        routes=[Route("/", _read_body, methods=["POST"])],
        exception_handlers={RequestBodyTooLarge: request_body_too_large_handler},
    )
    app.add_middleware(BodySizeLimitMiddleware, max_body_size=limit)
    app.add_middleware(CorrelationIdMiddleware)
    return app


def _chunks(total: int, size: int = 100):
    sent = 0
    while sent < total:
        piece = min(size, total - sent)
        sent += piece
        yield b"x" * piece


def test_a_chunked_body_over_the_limit_is_cut_off_with_413():
    """Without a Content-Length the header check cannot see the size: the bytes have to be counted
    as they arrive, or a chunked upload bypasses the limit completely."""
    response = TestClient(_limited_app(1024)).post("/", content=_chunks(5000))

    assert response.status_code == 413
    assert response.json()["code"] == "VALIDATION-08"
    assert response.json()["request_id"] == response.headers["X-Request-Id"]


def test_a_chunked_body_within_the_limit_passes():
    response = TestClient(_limited_app(1024)).post("/", content=_chunks(1000))

    assert response.status_code == 200
    assert response.json() == {"read": 1000}


def test_a_chunked_body_exactly_at_the_limit_passes():
    assert TestClient(_limited_app(1024)).post("/", content=_chunks(1024)).status_code == 200
