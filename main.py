import logging
import os

from fastapi import Depends, FastAPI, Request, status
from fastapi.exception_handlers import http_exception_handler as default_http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.cors import CORSMiddleware

from api.dependencies.dependencies import get_db
from api.routers import customers, orders
from api.security.middleware import (
    BodySizeLimitMiddleware,
    CorrelationIdMiddleware,
    RequestIdFilter,
    SecurityHeadersMiddleware,
    get_request_id,
)
from api.security.rate_limit import limiter
from api.utils.custom_api_exception import CustomAPIException

_SAFE_DEFAULT_ENVS = {"development", "test"}
APP_ENV = os.environ.get("APP_ENV", "development")
IS_PRODUCTION = APP_ENV not in _SAFE_DEFAULT_ENVS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - [%(request_id)s] - %(message)s",
)
# O filtro precisa estar no Handler, não no Logger raiz: um record de um logger filho
# (httpx, uvicorn, ...) propaga direto para os handlers do raiz sem passar pelos filtros do
# raiz (Logger.filters só é checado no logger que originou o record) — só assim todo log da
# aplicação, inclusive de bibliotecas de terceiros, ganha o campo %(request_id)s.
for _handler in logging.getLogger().handlers:
    _handler.addFilter(RequestIdFilter())

logger = logging.getLogger(__name__)

# CORS falha o startup se a config vier vazia em produção — nunca sobe com CORS aberto
# por uma variável de ambiente incompleta (ver skill fastapi-feature, baseline de segurança).
_cors_origins = [origin for origin in os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",") if origin]
if IS_PRODUCTION and not _cors_origins:
    raise RuntimeError(
        "CORS_ALLOWED_ORIGINS must be set with at least one origin when APP_ENV=production"
    )

app = FastAPI(
    title="FastAPI Order API",
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
    openapi_url=None if IS_PRODUCTION else "/openapi.json",
)

app.state.limiter = limiter

# add_middleware empilha de dentro para fora: o ULTIMO registrado e o mais externo. A ordem abaixo faz
# toda resposta (inclusive as recusas precoces: 413, 400 de Content-Length, preflight de CORS) passar
# por correlation id e security headers.
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(BodySizeLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CorrelationIdMiddleware)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    # slowapi ja devolve 429 por conta propria via detail (string com o limite excedido);
    # so reembalamos no mesmo formato {message, code, params, request_id} usado pelo resto
    # da aplicacao, em vez de deixar essa ser a unica resposta de erro fora do padrao.
    content = {
        "message": "Rate limit exceeded",
        "code": "RATE-00",
        "params": {"detail": str(exc.detail)},
        "request_id": get_request_id(),
    }
    return JSONResponse(status_code=status.HTTP_429_TOO_MANY_REQUESTS, content=content)


@app.exception_handler(CustomAPIException)
async def custom_api_exception_handler(request: Request, exc: CustomAPIException):
    # exc.detail e tipado como str pela base (Starlette HTTPException), mas
    # CustomAPIException sempre passa um dict {message, code, params} em runtime.
    content = {**exc.detail, "request_id": get_request_id()}  # type: ignore[dict-item]
    return JSONResponse(status_code=exc.status_code, content=content)


_AUTH_ERRORS = {
    status.HTTP_401_UNAUTHORIZED: ("Authentication required", "AUTH-01"),
    status.HTTP_403_FORBIDDEN: ("Access denied", "AUTH-02"),
}


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    # 401/403 come from the auth dependencies as plain HTTPException; they get the same
    # {message, code, params, request_id} body as every other error instead of {"detail": ...}.
    # The detail ("Invalid token", "Insufficient role") is deliberately not echoed to the client.
    if exc.status_code in _AUTH_ERRORS:
        message, code = _AUTH_ERRORS[exc.status_code]
        content = {"message": message, "code": code, "params": {}, "request_id": get_request_id()}
        return JSONResponse(status_code=exc.status_code, content=content, headers=exc.headers)
    return await default_http_exception_handler(request, exc)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    content = None
    if len(exc.errors()) > 0:
        err = exc.errors()[0]  # apenas o primeiro erro
        content = {
            "message": f"{err['msg']}.",
            "code": "VALIDATION-01",
            "params": {"field": err["loc"][-1]},
            "request_id": get_request_id(),
        }
    return JSONResponse(content=content, status_code=status.HTTP_400_BAD_REQUEST)


_UNIQUE_CONFLICTS = {
    "uq_customers_tax_id": ("Customer with this tax_id already exists", "CONFLICT-01"),
    "uq_customers_passport_number": ("Customer with this passport_number already exists", "CONFLICT-02"),
}


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    # The unique indexes are the real guarantee under concurrency: the service-level check only gives the
    # common case a readable 409 without a failed write. Whatever slips past it (two simultaneous creates)
    # lands here and is still a 409 - never a 500 - and never echoes the offending value (PII).
    constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
    message, code = _UNIQUE_CONFLICTS.get(constraint, ("Data integrity violation", "CONFLICT-04"))
    content = {"message": message, "code": code, "params": {}, "request_id": get_request_id()}
    return JSONResponse(content=content, status_code=status.HTTP_409_CONFLICT)


@app.exception_handler(StaleDataError)
async def stale_data_exception_handler(request: Request, exc: StaleDataError):
    content = {
        "message": "Record was modified by another request",
        "code": "CONFLICT-00",
        "params": {},
        "request_id": get_request_id(),
    }
    return JSONResponse(content=content, status_code=status.HTTP_409_CONFLICT)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # Catch-all para o que nenhum handler acima tratou: loga a stack trace completa com o
    # request_id de correlação (ver RequestIdFilter) para investigação, mas nunca devolve
    # detalhes internos (tipo da exceção, stack trace, mensagem) ao client — evita vazar
    # estrutura interna da aplicação em produção.
    logger.exception("unhandled_exception: path=%s method=%s", request.url.path, request.method)
    content = {
        "message": "Internal server error",
        "code": "INTERNAL-00",
        "params": {},
        "request_id": get_request_id(),
    }
    return JSONResponse(content=content, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


app.include_router(customers.router)
app.include_router(orders.router)


@app.get("/health", summary="Health check")
@limiter.exempt
def health_check(db=Depends(get_db)):
    """Confere conectividade real com o banco (`SELECT 1`)."""
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    # Conveniência de dev local (`python main.py`); em produção o processo sobe via
    # `uvicorn` CLI/container, não por este bloco.
    uvicorn.run(app, host="0.0.0.0", port=8000)  # nosec B104
