import logging
import os

from fastapi import Depends, FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from sqlalchemy import text
from sqlalchemy.orm.exc import StaleDataError
from starlette.middleware.cors import CORSMiddleware

from api.dependencies.dependencies import get_db
from api.routers import customers, orders
from api.security.middleware import (
    BodySizeLimitMiddleware,
    CorrelationIdMiddleware,
    RequestIdFilter,
    SecurityHeadersMiddleware,
)
from api.utils.custom_api_exception import CustomAPIException

APP_ENV = os.environ.get("APP_ENV", "development")
IS_PRODUCTION = APP_ENV == "production"

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

limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(SlowAPIMiddleware)
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(BodySizeLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(CustomAPIException)
async def custom_api_exception_handler(request: Request, exc: CustomAPIException):
    return JSONResponse(status_code=exc.status_code, content=exc.detail)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    content = None
    if len(exc.errors()) > 0:
        err = exc.errors()[0]  # apenas o primeiro erro
        content = {
            "message": f"{err['msg']}.",
            "code": "VALIDATION-01",
            "params": {"field": err["loc"][-1]},
        }
    return JSONResponse(content=content, status_code=status.HTTP_400_BAD_REQUEST)


@app.exception_handler(StaleDataError)
async def stale_data_exception_handler(request: Request, exc: StaleDataError):
    content = {"message": "Record was modified by another request", "code": "CONFLICT-00", "params": {}}
    return JSONResponse(content=content, status_code=status.HTTP_409_CONFLICT)


app.include_router(customers.router)
app.include_router(orders.router)


@app.get("/health", summary="Health check")
def health_check(db=Depends(get_db)):
    """Confere conectividade real com o banco (`SELECT 1`)."""
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
