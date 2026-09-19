import os

# Must run before any test module imports api.dependencies.dependencies (directly or via
# main.py) - that module reads JWT_PUBLIC_KEY_PATH at import time and raises if unset.
# setdefault (not setenv) so a test that explicitly wants a different/missing value via
# monkeypatch still controls its own scope.
from tests.utils.jwt_keys import PUBLIC_KEY_PATH  # noqa: E402

os.environ.setdefault("JWT_PUBLIC_KEY_PATH", PUBLIC_KEY_PATH)
