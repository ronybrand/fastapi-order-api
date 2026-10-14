import jwt
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from api.dependencies.dependencies import decode_access_token


def rate_limit_key(request: Request) -> str:
    """Quem tem token valido e limitado por usuario (`sub`); o resto, por endereco. Por endereco
    sozinho, todos os usuarios atras do mesmo proxy/NAT dividiriam um unico balde, e um usuario
    trocando de IP escaparia do dele. O token e verificado por inteiro (decode_access_token):
    uma chave de limite forjada nao serve para fugir do limite nem para gastar o balde de outro."""
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() == "bearer" and token:
        try:
            return f"user:{decode_access_token(token)['sub']}"
        except jwt.PyJWTError:
            pass
    return get_remote_address(request)


# Instancia unica compartilhada entre main.py (registro do middleware/handler) e os
# routers (decorators @limiter.limit(...) por rota) - modulo proprio para evitar import
# circular, ja que main.py importa os routers e os routers precisam do limiter.
limiter = Limiter(key_func=rate_limit_key, default_limits=["100/minute"])
