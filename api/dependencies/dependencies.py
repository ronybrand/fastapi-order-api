import os
from dataclasses import dataclass
from pathlib import Path

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api.security.roles import ROLE_USER
from database import SessionLocal

# This service only verifies tokens - it never issues them (no /auth/login endpoint here).
# JWT_PUBLIC_KEY_PATH must point at the public half of whatever key pair the real token
# issuer signs with (RS256). Unlike the shared HS256 secret this replaced (see ADR 0003),
# leaking this file grants no ability to mint tokens, only to verify them - so there is no
# "insecure default" to fail-fast against here: an unset path just can't work at all, in
# every environment, and fails loudly for that reason instead.
JWT_PUBLIC_KEY_PATH = os.environ.get("JWT_PUBLIC_KEY_PATH")
if JWT_PUBLIC_KEY_PATH is None:
    raise RuntimeError(
        "JWT_PUBLIC_KEY_PATH must be set - this service only verifies tokens (RS256), it never issues them"
    )

JWT_PUBLIC_KEY = Path(JWT_PUBLIC_KEY_PATH).read_bytes()
JWT_ALGORITHM = "RS256"
JWT_AUDIENCE = os.environ.get("JWT_AUDIENCE", "fastapi-order-api")
JWT_ISSUER = os.environ.get("JWT_ISSUER", "fastapi-order-api")

_bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail=detail, headers={"WWW-Authenticate": "Bearer"}
    )


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
        raise _unauthorized("Not authenticated")

    try:
        payload = jwt.decode(
            credentials.credentials,
            JWT_PUBLIC_KEY,
            algorithms=[JWT_ALGORITHM],
            audience=JWT_AUDIENCE,
            issuer=JWT_ISSUER,
            # PyJWT only checks a claim that is present: without "require" a token with no exp (valid
            # forever) or no aud/iss would pass. The signing issuer must set all four.
            options={"require": ["exp", "sub", "aud", "iss"]},
        )
    except jwt.PyJWTError as exc:
        raise _unauthorized("Invalid token") from exc

    subject = payload.get("sub")
    if subject is None:
        raise _unauthorized("Invalid token")

    roles = payload.get("roles", [ROLE_USER])
    # A string would turn `role in roles` into a substring test ("admin" in "superadmin").
    if not isinstance(roles, list) or not all(isinstance(role, str) for role in roles):
        raise _unauthorized("Invalid token")

    return CurrentUser(id=subject, roles=roles)


def require_role(role: str):
    """Factory de dependency: autenticado-vs-admin é a granularidade atual do projeto (ver
    skill fastapi-feature, "Autenticação e Autorização") — não crie um papel de domínio
    isolado sem essa decisão ser tomada explicitamente com o time."""

    def _check(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if role not in current_user.roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return current_user

    return _check
