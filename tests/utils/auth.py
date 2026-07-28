from jose import jwt

from api.dependencies.dependencies import JWT_ALGORITHM, JWT_AUDIENCE, JWT_ISSUER, JWT_SECRET
from api.security.roles import ROLE_ADMIN, ROLE_USER


def build_token(subject: str = "test-user", roles: list[str] | None = None, **overrides) -> str:
    payload = {
        "sub": subject,
        "roles": roles if roles is not None else [ROLE_USER],
        "aud": JWT_AUDIENCE,
        "iss": JWT_ISSUER,
    }
    payload.update(overrides)
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def auth_headers(subject: str = "test-user", roles: list[str] | None = None) -> dict:
    return {"Authorization": f"Bearer {build_token(subject, roles)}"}


def admin_headers(subject: str = "test-admin") -> dict:
    return auth_headers(subject, roles=[ROLE_ADMIN])


def invalid_audience_headers(subject: str = "test-user") -> dict:
    token = jwt.encode(
        {"sub": subject, "roles": [ROLE_USER], "aud": "wrong-audience", "iss": JWT_ISSUER},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )
    return {"Authorization": f"Bearer {token}"}
