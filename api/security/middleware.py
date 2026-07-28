import contextvars
import logging
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

MAX_BODY_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

_request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    """Inclui o correlation-id da requisição atual em todo registro de log, sem precisar
    passá-lo manualmente em cada camada."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_ctx.get()
        return True


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))
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


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Rejeita (413) requisições cujo Content-Length declarado excede o teto, antes do corpo
    ser lido/desserializado pelo Pydantic — evita alocar memória para um payload gigante."""

    def __init__(self, app, max_body_size: int = MAX_BODY_SIZE_BYTES):
        super().__init__(app)
        self.max_body_size = max_body_size

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length is not None and int(content_length) > self.max_body_size:
            return JSONResponse(
                status_code=413,
                content={
                    "message": "Request body too large",
                    "code": "VALIDATION-08",
                    "params": {"max_bytes": self.max_body_size},
                },
            )
        return await call_next(request)
