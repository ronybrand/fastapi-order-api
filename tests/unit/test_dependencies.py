import importlib
import sys

import pytest


def _reload_dependencies_module():
    sys.modules.pop("api.dependencies.dependencies", None)
    return importlib.import_module("api.dependencies.dependencies")


def test_missing_jwt_public_key_path_raises(monkeypatch):
    monkeypatch.delenv("JWT_PUBLIC_KEY_PATH", raising=False)

    with pytest.raises(RuntimeError):
        _reload_dependencies_module()


def test_valid_jwt_public_key_path_loads_the_key_bytes(monkeypatch, tmp_path):
    key_file = tmp_path / "public.pem"
    key_bytes = b"-----BEGIN PUBLIC KEY-----\nfake-for-this-test-only\n-----END PUBLIC KEY-----\n"
    key_file.write_bytes(key_bytes)
    monkeypatch.setenv("JWT_PUBLIC_KEY_PATH", str(key_file))

    module = _reload_dependencies_module()

    assert module.JWT_PUBLIC_KEY == key_bytes
    assert module.JWT_ALGORITHM == "RS256"
