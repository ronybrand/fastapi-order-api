import os
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from api.security.roles import ROLE_USER
from database import SessionLocal

_DEFAULT_JWT_SECRET = "insecure-dev-secret-change-me"
JWT_SECRET = os.environ.get("JWT_SECRET", _DEFAULT_JWT_SECRET)
JWT_ALGORITHM = "HS256"
JWT_AUDIENCE = os.environ.get("JWT_AUDIENCE", "fastapi-order-api")
JWT_ISSUER = os.environ.get("JWT_ISSUER", "fastapi-order-api")

# Mesma política do CORS em main.py, mas com allowlist em vez de blocklist: um APP_ENV
# esquecido ou desconhecido (ex.: variável não propagada pelo orquestrador) deve falhar
# fechado, não abrir a porta pro segredo default hardcoded no código-fonte, que permitiria
# forjar qualquer token válido.
_SAFE_DEFAULT_SECRET_ENVS = {"development", "test"}
if os.environ.get("APP_ENV", "development") not in _SAFE_DEFAULT_SECRET_ENVS and JWT_SECRET == _DEFAULT_JWT_SECRET:
    raise RuntimeError("JWT_SECRET must be set to a non-default value outside development/test")

_bearer_scheme = HTTPBearer(auto_error=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@dataclass(frozen=True)
class CurrentUser:
    id: str
    roles: list[str]


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> CurrentUser:
    """Decodifica e valida o Bearer token num único ponto central — nunca duplique essa
    validação por router. Toda rota protegida declara `Depends(get_current_user)`."""
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    try:
        payload = jwt.decode(
            credentials.credentials,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            audience=JWT_AUDIENCE,
            issuer=JWT_ISSUER,
        )
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    subject = payload.get("sub")
    if subject is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    return CurrentUser(id=subject, roles=payload.get("roles", [ROLE_USER]))


def require_role(role: str):
    """Factory de dependency: autenticado-vs-admin é a granularidade atual do projeto (ver
    skill fastapi-feature, "Autenticação e Autorização") — não crie um papel de domínio
    isolado sem essa decisão ser tomada explicitamente com o time."""

    def _check(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if role not in current_user.roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return current_user

    return _check
