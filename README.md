# fastapi-order-api

Implementação do domínio de Order Management (ver `DOMAIN.md` original em `java-order-api`)
em FastAPI, seguindo as convenções descritas na skill `fastapi-feature`
(`.claude/skills/fastapi-feature/SKILL.md`, não versionada — ver `.gitignore`).

## Domínio

`Customer (1) ──< Order (1) ──< Item`. Ver o `DOMAIN.md` de referência para as regras de
negócio completas (máquina de estado `OPEN → CONFIRMED → CANCELED`, unicidade de
`tax_id`/`passport_number`, limite de 200 itens por order, concorrência otimista em `Order`,
evento `OrderStatusChangedEvent` em `confirm()`/`cancel()`).

## Rodando localmente

Requer Postgres (ex. `docker run -e POSTGRES_PASSWORD=postgres -e POSTGRES_USER=postgres
-e POSTGRES_DB=orders -p 5432:5432 postgres:16`) e as variáveis de ambiente `DATABASE_URL`,
`JWT_SECRET`, `JWT_AUDIENCE`, `JWT_ISSUER`, `CORS_ALLOWED_ORIGINS` (obrigatória apenas com
`APP_ENV=production`).

```
pip install -r requirements.txt
alembic upgrade head
uvicorn main:app --reload
```

## Testes

- `pytest tests/unit` — mockado, sem banco, roda em qualquer ambiente.
- `pytest tests/integration` — Postgres real via Testcontainers, requer Docker local.

## Qualidade estática

```
ruff check .
mypy api
```
