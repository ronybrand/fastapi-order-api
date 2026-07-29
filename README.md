# fastapi-order-api

[![CI](https://github.com/ronybrand/fastapi-order-api/actions/workflows/ci.yml/badge.svg)](https://github.com/ronybrand/fastapi-order-api/actions/workflows/ci.yml)
[![CodeQL](https://github.com/ronybrand/fastapi-order-api/actions/workflows/codeql.yml/badge.svg)](https://github.com/ronybrand/fastapi-order-api/actions/workflows/codeql.yml)

Implementação do domínio de Order Management em FastAPI, seguindo as convenções descritas
na skill `fastapi-feature` (`.claude/skills/fastapi-feature/SKILL.md`, não versionada — ver
`.gitignore`).

## Domínio

Domínio simples de gestão de pedidos com dois agregados:

```
Customer (1) ──< Order (1) ──< Item
```

Fora de escopo: pagamento, estoque, catálogo de produtos, envio/frete.

### Entidades

#### Customer

| Campo | Tipo | Regras |
|---|---|---|
| `id` | UUID | gerado |
| `name` | string | obrigatório, `min_length=1` |
| `tax_id` | string | obrigatório, **único**, padrão `^[A-Za-z0-9./-]{5,20}$` |
| `passport_number` | string | opcional, **único** quando presente, padrão ICAO `^[A-Z0-9]{6,9}$` |
| `email` | string | obrigatório, validado via `EmailStr` (Pydantic) |
| `deleted_at` | datetime | soft-delete (nulo = ativo) |

- `tax_id`, `passport_number` e `email` são PII — nunca logados em texto claro
  (`mask_sensitive()`, ver `api/utils/sensitive.py`).

#### Order (aggregate root)

| Campo | Tipo | Regras |
|---|---|---|
| `id` | UUID | gerado |
| `customer_id` | UUID | obrigatório, precisa referenciar um customer existente (`VALIDATION-07`) |
| `items` | lista de Item | composição — ciclo de vida atrelado ao Order, máx. `MAX_ITEMS_PER_ORDER` (200) |
| `total` | decimal | **derivado**, recalculado a cada mutação de itens |
| `status` | enum `OrderStatus` | `OPEN → CONFIRMED → CANCELED`, default `OPEN` |
| `version` | inteiro | controle de concorrência otimista (SQLAlchemy `StaleDataError` → `CONFLICT-00`) |

- `confirm()` só é permitido a partir de `OPEN` e exige ao menos 1 item; falha com
  `VALIDATION-04` (status inválido) ou `VALIDATION-03` (sem itens).
- `cancel()` é permitido a partir de qualquer status exceto `CANCELED` (`VALIDATION-08`).
- Enquanto `OPEN`, itens podem ser adicionados/removidos livremente (`is_editable`);
  fora disso, `VALIDATION-02`.

#### Item (filho de Order)

| Campo | Tipo | Regras |
|---|---|---|
| `id` | UUID | gerado |
| `order_id` | UUID | obrigatório |
| `description` | string | obrigatório, não-branco, `max_length=255` |
| `unit_price` | decimal | obrigatório, positivo (`gt=0`), máx. 2 casas decimais |
| `quantity` | inteiro | obrigatório, positivo (`gt=0`) |

- Subtotal do item = `unit_price * quantity` (calculado, não persistido).

### Evento `OrderStatusChangedEvent`

Disparado ao final de `confirm()`/`cancel()`, somente quando o customer tem `email`
não-vazio. Carrega `order_id`, `customer_email`, `customer_name`, `old_status`,
`new_status`, `total_amount` e `changed_at`. Logado (log estruturado, e-mail nunca em
texto claro) e publicado no RabbitMQ (`RABBITMQ_URL`) para processamento assíncrono pelo
worker (`worker.py`), que envia o e-mail de fato via SMTP (`SMTP_HOST`/`SMTP_PORT`/
`SMTP_FROM`, default Mailpit local), renderizado via Jinja2 a partir de
`templates/email/order_status_changed.html`. Falha de broker/SMTP nunca derruba a
requisição HTTP nem o commit do pedido (ver `api/events/rabbitmq_publisher.py`).

### Catálogo de erros

**Validação (400)**
| Código | Descrição |
|---|---|
| `VALIDATION-01` | corpo da requisição inválido (schema Pydantic) |
| `VALIDATION-02` | order não editável no status atual |
| `VALIDATION-03` | confirmar order sem itens |
| `VALIDATION-04` | transição de status inválida ao confirmar |
| `VALIDATION-05` | valor de filtro inválido na busca |
| `VALIDATION-06` | campo de ordenação desconhecido na busca |
| `VALIDATION-07` | customer inexistente ao criar order |
| `VALIDATION-08` | cancelar order já cancelada |

**Não encontrado (404)**
| Código | Descrição |
|---|---|
| `RESOURCE-NOT-FOUND-01` | customer não encontrado |
| `RESOURCE-NOT-FOUND-02` | order não encontrada |
| `RESOURCE-NOT-FOUND-03` | item não encontrado |

**Conflito (409)**
| Código | Descrição |
|---|---|
| `CONFLICT-00` | modificação concorrente (`StaleDataError`, lock otimista) |
| `CONFLICT-01` | `tax_id` duplicado |
| `CONFLICT-02` | `passport_number` duplicado |
| `CONFLICT-03` | exclusão de customer com orders associados |

**Outros**
| Código | Descrição |
|---|---|
| `INTERNAL-00` | erro inesperado não tratado |

## Endpoints

### `/orders` (requer usuário autenticado)

| Método | Path | Descrição |
|---|---|---|
| POST | `/orders` | Criar order |
| GET | `/orders/search` | Buscar orders (query params) |
| POST | `/orders/search` | Buscar orders (body) |
| GET | `/orders/{order_id}` | Obter order por id |
| DELETE | `/orders/{order_id}` | Excluir (soft) order |
| POST | `/orders/{order_id}/items` | Adicionar item |
| PATCH | `/orders/{order_id}/items/{item_id}` | Atualizar quantidade do item |
| DELETE | `/orders/{order_id}/items/{item_id}` | Remover item |
| POST | `/orders/{order_id}/confirm` | Confirmar order |
| POST | `/orders/{order_id}/cancel` | Cancelar order |

### `/customers` (mutações requerem `ROLE_ADMIN`; leituras requerem usuário autenticado)

| Método | Path | Descrição |
|---|---|---|
| POST | `/customers` | Criar customer (admin) |
| GET | `/customers/search` | Buscar customers (query params) |
| POST | `/customers/search` | Buscar customers (body) |
| GET | `/customers/{customer_id}` | Obter customer por id |
| PUT | `/customers/{customer_id}` | Atualizar customer (admin) |
| DELETE | `/customers/{customer_id}` | Excluir (soft) customer (admin) |

Contrato completo (schemas de request/response) sempre disponível no OpenAPI gerado
automaticamente pelo FastAPI: `/docs` (Swagger UI) e `/openapi.json`, desabilitados apenas
com `APP_ENV=production`.

## Rodando localmente

Requer Postgres (ex. `docker run -e POSTGRES_PASSWORD=postgres -e POSTGRES_USER=postgres
-e POSTGRES_DB=orders -p 5432:5432 postgres:16`) e RabbitMQ + Mailpit
(`docker compose up rabbitmq mailpit`), além das variáveis de ambiente `DATABASE_URL`,
`JWT_SECRET`, `JWT_AUDIENCE`, `JWT_ISSUER`, `CORS_ALLOWED_ORIGINS` (obrigatória apenas com
`APP_ENV=production`), `RABBITMQ_URL` (default `amqp://guest:guest@localhost:5672/`) e
`SMTP_HOST`/`SMTP_PORT`/`SMTP_FROM` (default Mailpit: `localhost`/`1025`/
`no-reply@order-api.local`). Mailpit web UI para inspecionar os e-mails recebidos:
`http://localhost:8025`.

```
pip install -r requirements.txt
alembic upgrade head
uvicorn main:app --reload
python worker.py   # processo separado: consome order.status.changed
```

## Testes e qualidade

- `pytest tests/unit` — mockado, sem banco, roda em qualquer ambiente.
- `pytest tests/integration` — Postgres real via Testcontainers, requer Docker local.

```
ruff check .
mypy api worker.py
bandit -r api main.py database.py worker.py
make verify   # gate local único: ruff → mypy → bandit → pytest com cobertura
```

`make verify` reproduz o `ci.yml` num único comando local. Cobertura mínima em
`[tool.coverage.report] fail_under = 80` (`pyproject.toml`).
