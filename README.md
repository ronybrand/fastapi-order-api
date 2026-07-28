# fastapi-order-api

Implementação do domínio de Order Management em FastAPI, seguindo as convenções descritas
na skill `fastapi-feature` (`.claude/skills/fastapi-feature/SKILL.md`, não versionada — ver
`.gitignore`).

## Domínio

`Customer (1) ──< Order (1) ──< Item`.

- **Customer**: `name`, `tax_id` (único), `passport_number` (opcional, único quando
  preenchido) e `email`. Soft delete (`deleted_at`).
- **Order**: pertence a um `Customer`. Máquina de estado `status`:
  `OPEN → CONFIRMED → CANCELED`.
  - `confirm()` só é permitido a partir de `OPEN` e exige ao menos 1 item; falha com
    `VALIDATION-04` (status inválido) ou `VALIDATION-03` (sem itens).
  - `cancel()` é permitido a partir de qualquer status exceto `CANCELED`
    (`VALIDATION-08` se já cancelado).
  - Enquanto `OPEN`, itens podem ser adicionados/removidos livremente (`is_editable`).
  - Concorrência otimista via coluna `version`: o SQLAlchemy verifica/incrementa `version`
    a cada `UPDATE` e lança `StaleDataError` se a linha mudou desde a leitura — tratado
    globalmente em `main.py`.
  - Soft delete (`deleted_at`).
- **Item**: pertence a um `Order` (cascade `all, delete-orphan` — não existe fora do
  `Order`), com `description`, `unit_price` e `quantity`. Limite de **200 itens por
  order** (`MAX_ITEMS_PER_ORDER`, validado no schema de entrada).
- **Evento `OrderStatusChangedEvent`**: disparado ao final de `confirm()`/`cancel()`,
  somente quando o customer tem `email` não-vazio. Carrega `order_id`, `customer_email`,
  `customer_name`, `old_status`, `new_status`, `total_amount` e `changed_at`. Publicado de
  forma síncrona (log estruturado) por não haver hoje serviço externo de notificação
  integrado; o e-mail nunca é logado em texto claro.

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
