import importlib
import sys

import pytest


def _reload_dependencies_module():
    sys.modules.pop("api.dependencies.dependencies", None)
    return importlib.import_module("api.dependencies.dependencies")


def test_jwt_secret_default_raises_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("JWT_SECRET", raising=False)

    with pytest.raises(RuntimeError):
        _reload_dependencies_module()


def test_jwt_secret_explicit_value_allowed_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "a-real-production-secret")

    module = _reload_dependencies_module()

    assert module.JWT_SECRET == "a-real-production-secret"


def test_jwt_secret_default_allowed_outside_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("JWT_SECRET", raising=False)

    module = _reload_dependencies_module()

    assert module.JWT_SECRET == "insecure-dev-secret-change-me"
