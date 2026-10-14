import os
from dataclasses import dataclass

_SAFE_DEFAULT_ENVS = {"development", "test"}
_LOCAL_BROKER_URL = "amqp://guest:guest@localhost:5672/"


def is_production() -> bool:
    # Mesma regra do main.py: qualquer APP_ENV desconhecido conta como producao.
    return os.environ.get("APP_ENV", "development") not in _SAFE_DEFAULT_ENVS


def rabbitmq_url() -> str:
    """URL do broker. O default guest/guest em texto claro so existe fora de producao; em producao a
    URL e obrigatoria e tem que ser amqps:// (a fila carrega e-mail e nome do cliente)."""
    url = os.environ.get("RABBITMQ_URL")
    if url is None:
        if is_production():
            raise RuntimeError("RABBITMQ_URL must be set when APP_ENV is not development/test")
        return _LOCAL_BROKER_URL
    if is_production() and not url.startswith("amqps://"):
        raise RuntimeError("RABBITMQ_URL must use amqps:// (TLS) when APP_ENV is not development/test")
    return url


@dataclass(frozen=True)
class SmtpSettings:
    host: str
    port: int
    from_addr: str
    starttls: bool
    user: str | None
    password: str | None


def smtp_settings() -> SmtpSettings:
    """Configuracao do SMTP. O default (localhost:1025 sem TLS) e o Mailpit do docker-compose; fora de
    desenvolvimento STARTTLS e obrigatorio, e credencial nunca trafega em conexao sem TLS."""
    starttls = os.environ.get("SMTP_STARTTLS", "false").lower() == "true"
    user = os.environ.get("SMTP_USER") or None
    if not starttls and (is_production() or user):
        raise RuntimeError("SMTP_STARTTLS=true is required in production and whenever SMTP_USER is set")
    return SmtpSettings(
        host=os.environ.get("SMTP_HOST", "localhost"),
        port=int(os.environ.get("SMTP_PORT", "1025")),
        from_addr=os.environ.get("SMTP_FROM", "no-reply@order-api.local"),
        starttls=starttls,
        user=user,
        password=os.environ.get("SMTP_PASSWORD") if user else None,
    )
