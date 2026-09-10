from slowapi import Limiter
from slowapi.util import get_remote_address

# Instancia unica compartilhada entre main.py (registro do middleware/handler) e os
# routers (decorators @limiter.limit(...) por rota) - modulo proprio para evitar import
# circular, ja que main.py importa os routers e os routers precisam do limiter.
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])
