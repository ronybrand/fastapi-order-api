import jwt
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from api.dependencies.dependencies import (
    JWT_ALGORITHM,
    JWT_AUDIENCE,
    JWT_ISSUER,
    JWT_PUBLIC_KEY,
)


def rate_limit_key(request: Request) -> str:
    """Quem tem token valido e limitado por usuario (`sub`); o resto, por endereco. Por endereco
    sozinho, todos os usuarios atras do mesmo proxy/NAT dividiriam um unico balde, e um usuario
    trocando de IP escaparia do dele. O token e verificado por inteiro (assinatura, aud, iss, exp):
    uma chave de limite forjada nao serve para fugir do limite nem para gastar o balde de outro."""
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() == "bearer" and token:
        try:
            payload = jwt.decode(
                token,
                JWT_PUBLIC_KEY,
                algorithms=[JWT_ALGORITHM],
                audience=JWT_AUDIENCE,
                issuer=JWT_ISSUER,
                options={"require": ["exp", "sub", "aud", "iss"]},
            )
            return f"user:{payload['sub']}"
        except jwt.PyJWTError:
            pass
    return get_remote_address(request)


# Instancia unica compartilhada entre main.py (registro do middleware/handler) e os
# routers (decorators @limiter.limit(...) por rota) - modulo proprio para evitar import
# circular, ja que main.py importa os routers e os routers precisam do limiter.
limiter = Limiter(key_func=rate_limit_key, default_limits=["100/minute"])
