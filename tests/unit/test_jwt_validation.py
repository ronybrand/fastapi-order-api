import base64
import json
import time

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from api.dependencies.dependencies import (
    JWT_AUDIENCE,
    JWT_ISSUER,
    JWT_PUBLIC_KEY,
    get_current_user,
)
from api.security.roles import ROLE_USER
from tests.utils.auth import build_token
from tests.utils.jwt_keys import PRIVATE_KEY_PEM


def _authenticate(token: str):
    return get_current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token))


def _sign(**claims) -> str:
    payload = {
        "sub": "u-1",
        "roles": [ROLE_USER],
        "aud": JWT_AUDIENCE,
        "iss": JWT_ISSUER,
        "exp": int(time.time()) + 3600,
    }
    payload.update(claims)
    payload = {key: value for key, value in payload.items() if value is not None}
    return jwt.encode(payload, PRIVATE_KEY_PEM, algorithm="RS256")


def _assert_unauthorized(token: str) -> None:
    with pytest.raises(HTTPException) as exc:
        _authenticate(token)

    assert exc.value.status_code == 401
    assert exc.value.headers == {"WWW-Authenticate": "Bearer"}


def _b64(data: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


def test_a_well_formed_token_authenticates():
    user = _authenticate(build_token("u-1"))

    assert user.id == "u-1"
    assert user.roles == [ROLE_USER]


def test_token_without_exp_is_rejected():
    _assert_unauthorized(_sign(exp=None))


def test_expired_token_is_rejected():
    _assert_unauthorized(_sign(exp=int(time.time()) - 60))


def test_token_with_the_wrong_issuer_is_rejected():
    _assert_unauthorized(_sign(iss="someone-else"))


def test_token_without_audience_is_rejected():
    _assert_unauthorized(_sign(aud=None))


def test_unsigned_token_with_alg_none_is_rejected():
    header = _b64({"alg": "none", "typ": "JWT"})
    payload = _b64(
        {"sub": "u-1", "aud": JWT_AUDIENCE, "iss": JWT_ISSUER, "exp": int(time.time()) + 3600}
    )

    _assert_unauthorized(f"{header}.{payload}.")


def test_hs256_token_signed_with_the_public_key_is_rejected():
    """Algorithm-confusion attack: the public key is public, so an HS256 signature made with it
    must never validate - only RS256 is accepted."""
    header = _b64({"alg": "HS256", "typ": "JWT"})
    payload = _b64(
        {"sub": "u-1", "aud": JWT_AUDIENCE, "iss": JWT_ISSUER, "exp": int(time.time()) + 3600}
    )
    import hashlib
    import hmac

    signing_input = f"{header}.{payload}".encode()
    signature = base64.urlsafe_b64encode(
        hmac.new(JWT_PUBLIC_KEY, signing_input, hashlib.sha256).digest()
    ).rstrip(b"=")

    _assert_unauthorized(f"{header}.{payload}.{signature.decode()}")


def test_garbage_token_is_rejected():
    _assert_unauthorized("not-a-jwt")


@pytest.mark.parametrize("roles", ["admin", "superadmin", {"admin": True}, ["user", 1], 7])
def test_roles_claim_that_is_not_a_list_of_strings_is_rejected(roles):
    _assert_unauthorized(_sign(roles=roles))


def test_missing_roles_claim_defaults_to_plain_user():
    assert _authenticate(_sign(roles=None)).roles == [ROLE_USER]
