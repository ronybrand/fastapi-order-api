import pytest

from api.utils.messaging_config import rabbitmq_url, smtp_settings


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("APP_ENV", "RABBITMQ_URL", "SMTP_HOST", "SMTP_PORT", "SMTP_FROM", "SMTP_STARTTLS",
                 "SMTP_USER", "SMTP_PASSWORD"):
        monkeypatch.delenv(name, raising=False)


# --- RabbitMQ ---
def test_development_keeps_the_local_broker_default():
    assert rabbitmq_url() == "amqp://guest:guest@localhost:5672/"


def test_production_refuses_to_fall_back_to_guest_credentials(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")

    with pytest.raises(RuntimeError, match="RABBITMQ_URL"):
        rabbitmq_url()


def test_production_requires_tls_to_the_broker(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("RABBITMQ_URL", "amqp://svc:secret@broker:5672/")

    with pytest.raises(RuntimeError, match="amqps"):
        rabbitmq_url()


def test_production_accepts_an_amqps_url(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("RABBITMQ_URL", "amqps://svc:secret@broker:5671/")

    assert rabbitmq_url() == "amqps://svc:secret@broker:5671/"


def test_development_accepts_a_plain_url(monkeypatch):
    monkeypatch.setenv("RABBITMQ_URL", "amqp://other:other@broker:5672/")

    assert rabbitmq_url() == "amqp://other:other@broker:5672/"


# --- SMTP ---
def test_development_defaults_to_the_local_mailpit():
    settings = smtp_settings()

    assert (settings.host, settings.port) == ("localhost", 1025)
    assert (settings.starttls, settings.user) == (False, None)


def test_production_requires_starttls(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")

    with pytest.raises(RuntimeError, match="SMTP_STARTTLS"):
        smtp_settings()


def test_credentials_are_never_sent_over_a_plain_connection_in_any_environment(monkeypatch):
    monkeypatch.setenv("SMTP_USER", "mailer")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")

    with pytest.raises(RuntimeError, match="SMTP_STARTTLS"):
        smtp_settings()


def test_production_with_starttls_and_credentials_is_valid(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SMTP_STARTTLS", "true")
    monkeypatch.setenv("SMTP_USER", "mailer")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("SMTP_PORT", "587")

    settings = smtp_settings()

    assert settings.starttls is True
    assert (settings.user, settings.password, settings.port) == ("mailer", "secret", 587)
