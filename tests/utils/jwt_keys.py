"""Throwaway RSA key pair generated once per test session (module import is cached by
Python), so every test signs/verifies against the same pair without a real key ever
touching disk outside a temp directory. Mirrors nest-order-api's JwtTestTokenFactory:
this service only verifies tokens (RS256, see ADR 0003) - the private key here plays the
role of an external token issuer the tests stand in for."""

import tempfile
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

PRIVATE_KEY_PEM = _private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
).decode("utf-8")

_public_pem = _private_key.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
)

_tmp_dir = tempfile.mkdtemp(prefix="fastapi-order-api-jwt-")
PUBLIC_KEY_PATH = str(Path(_tmp_dir) / "public.pem")
Path(PUBLIC_KEY_PATH).write_bytes(_public_pem)
