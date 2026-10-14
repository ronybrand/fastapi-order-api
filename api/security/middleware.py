import contextvars
import logging
import uuid

from starlette.datastructures import Headers
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

MAX_BODY_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

_request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


def get_request_id() -> str:
    """Le o correlation-id da requisicao atual (mesmo contextvar usado pelo
    RequestIdFilter), para incluir no corpo de respostas de erro alem do
    header X-Request-Id."""
    return _request_id_ctx.get()


class RequestIdFilter(logging.Filter):
    """Inclui o correlation-id da requisição atual em todo registro de log, sem precisar
    passá-lo manualmente em cada camada."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_ctx.get()
        return True


def _accepted_request_id(supplied: str | None) -> str:
    """O id vem do cliente e acaba em log, header e corpo de erro: so um UUID canonico e aceito;
    qualquer outra coisa (texto livre, quebra de linha, 10 KB de lixo) e descartada e substituida,
    o que fecha log forging e header injection."""
    if supplied is not None:
        try:
            parsed = uuid.UUID(supplied)
        except ValueError:
            parsed = None
        if parsed is not None and str(parsed) == supplied.lower():
            return str(parsed)
    return str(uuid.uuid4())


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = _accepted_request_id(request.headers.get("X-Request-Id"))
        token = _request_id_ctx.set(request_id)
        try:
            response = await call_next(request)
        finally:
            _request_id_ctx.reset(token)
        response.headers["X-Request-Id"] = request_id
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
        return response


class RequestBodyTooLarge(Exception):
    """Levantada de dentro do `receive` quando o corpo ja lido passa do teto (upload em chunks, sem
    Content-Length): vira 413 pelo handler registrado em main.py."""


def _error_body(message: str, code: str, params: dict) -> dict:
    return {"message": message, "code": code, "params": params, "request_id": get_request_id()}


def _too_large_body(max_bytes: int) -> dict:
    return _error_body("Request body too large", "VALIDATION-08", {"max_bytes": max_bytes})


async def request_body_too_large_handler(request: Request, exc: RequestBodyTooLarge):
    return JSONResponse(status_code=413, content=_too_large_body(MAX_BODY_SIZE_BYTES))


class BodySizeLimitMiddleware:
    """Limita o tamanho do corpo da requisicao. Content-Length declarado acima do teto (ou invalido) e
    recusado antes de qualquer leitura; sem Content-Length (Transfer-Encoding: chunked) os bytes sao
    contados conforme chegam e a leitura e interrompida ao passar do teto - so olhar o header deixaria
    um upload em chunks fugir do limite. ASGI puro (nao BaseHTTPMiddleware) para poder embrulhar o
    `receive`."""

    def __init__(self, app, max_body_size: int = MAX_BODY_SIZE_BYTES):
        self.app = app
        self.max_body_size = max_body_size

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        content_length = Headers(scope=scope).get("content-length")
        if content_length is not None:
            # int() on a non-numeric header used to raise (an unhandled 500).
            if not content_length.isascii() or not content_length.isdigit():
                response = JSONResponse(
                    status_code=400,
                    content=_error_body(
                        "Invalid Content-Length header", "VALIDATION-01", {"field": "content-length"}
                    ),
                )
                await response(scope, receive, send)
                return
            if int(content_length) > self.max_body_size:
                response = JSONResponse(status_code=413, content=_too_large_body(self.max_body_size))
                await response(scope, receive, send)
                return

        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_size:
                    raise RequestBodyTooLarge
            return message

        await self.app(scope, limited_receive, send)
