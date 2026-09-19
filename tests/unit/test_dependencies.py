import importlib
import os
import sys
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from jose import jwt

from tests.utils.jwt_keys import PRIVATE_KEY_PEM


def _reload_dependencies_module():
    sys.modules.pop("api.dependencies.dependencies", None)
    return importlib.import_module("api.dependencies.dependencies")


@pytest.fixture
def _restore_dependencies_module_after():
    """The two tests below reload api.dependencies.dependencies with a broken/missing
    JWT_PUBLIC_KEY_PATH, replacing the module in sys.modules - monkeypatch restores the env
    var, but not the module object it leaves behind. Anything importing from that module
    afterward (including other test files, depending on collection order) would get the
    broken version. Explicitly reloads with the real value once the test is done, regardless
    of monkeypatch's own teardown timing."""
    original = os.environ.get("JWT_PUBLIC_KEY_PATH")
    yield
    if original is not None:
        os.environ["JWT_PUBLIC_KEY_PATH"] = original
    _reload_dependencies_module()


def test_missing_jwt_public_key_path_raises(monkeypatch, _restore_dependencies_module_after):
    monkeypatch.delenv("JWT_PUBLIC_KEY_PATH", raising=False)

    with pytest.raises(RuntimeError):
        _reload_dependencies_module()


def test_valid_jwt_public_key_path_loads_the_key_bytes(
    monkeypatch, tmp_path, _restore_dependencies_module_after
):
    key_file = tmp_path / "public.pem"
    key_bytes = b"-----BEGIN PUBLIC KEY-----\nfake-for-this-test-only\n-----END PUBLIC KEY-----\n"
    key_file.write_bytes(key_bytes)
    monkeypatch.setenv("JWT_PUBLIC_KEY_PATH", str(key_file))

    module = _reload_dependencies_module()

    assert module.JWT_PUBLIC_KEY == key_bytes
    assert module.JWT_ALGORITHM == "RS256"


def test_get_db_rolls_back_and_reraises_on_exception():
    from api.dependencies.dependencies import get_db

    generator = get_db()
    db = next(generator)
    db.rollback = MagicMock()
    db.close = MagicMock()

    with pytest.raises(RuntimeError):
        generator.throw(RuntimeError("boom"))

    db.rollback.assert_called_once()
    db.close.assert_called_once()


def test_get_current_user_rejects_token_without_subject():
    from api.dependencies.dependencies import JWT_AUDIENCE, JWT_ISSUER, get_current_user

    token = jwt.encode(
        {"roles": ["USER"], "aud": JWT_AUDIENCE, "iss": JWT_ISSUER},
        PRIVATE_KEY_PEM,
        algorithm="RS256",
    )
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with pytest.raises(HTTPException) as exc:
        get_current_user(credentials)

    assert exc.value.status_code == 401
