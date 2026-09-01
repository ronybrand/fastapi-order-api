# fastapi-order-api

[![CI](https://github.com/ronybrand/fastapi-order-api/actions/workflows/ci.yml/badge.svg)](https://github.com/ronybrand/fastapi-order-api/actions/workflows/ci.yml)
[![CodeQL](https://github.com/ronybrand/fastapi-order-api/actions/workflows/codeql.yml/badge.svg)](https://github.com/ronybrand/fastapi-order-api/actions/workflows/codeql.yml)

Order Management domain implementation in FastAPI, following the conventions described
in the `fastapi-feature` skill (`.claude/skills/fastapi-feature/SKILL.md`, not version
controlled — see `.gitignore`).

## Request &amp; notification flow

**Order create/update (synchronous)**

```mermaid
flowchart LR
    Client -->|HTTPS| RateLimit["SlowAPIMiddleware<br/>(rate limit)"] --> Mid["Correlation / security / body-size middleware"] --> JWT["get_current_user<br/>(JWT dependency)"] --> Router[orders router] --> OrderService --> Repository[SQLAlchemy Session] --> DB[(PostgreSQL)]
```

`OrderService.confirm` / `OrderService.cancel` call `publish_order_status_changed` ⤵

**Notification (asynchronous)**

```mermaid
flowchart LR
    Event[OrderStatusChangedEvent] --> Publisher[publish_to_rabbitmq] -->|publish| Queue[[RabbitMQ order.status.changed]] -->|consume| Worker[worker.py] --> Email["_send_email (smtplib)"] --> Customer([Customer inbox])
    Worker -.->|retry / DLQ| Queue
```

`SlowAPIMiddleware` rate-limits every request first, ahead of the correlation-id,
security-headers and body-size middlewares; JWT auth is not middleware but a FastAPI
dependency (`get_current_user`, `python-jose`), declared on every order route and resolved
after routing. Creating or updating an order then runs synchronously through `OrderService`
and a SQLAlchemy `Session`, returning `201` for create and `200` for the update-style
endpoints (`204` for delete). A status change from `confirm()` or `cancel()` (not every
update, and only if the customer has an email) calls `publish_order_status_changed`, which
publishes to a RabbitMQ queue after the DB commit — failures there are only logged, never
propagated to the HTTP response. A separate `worker.py` process consumes the queue and sends
the email via SMTP, retrying up to 3 times with a fixed 2s backoff before nacking to the DLQ.
The two paths never block each other.

## Domain

Simple order management domain with two aggregates:

```
Customer (1) ──< Order (1) ──< Item
```

Out of scope: payment, inventory, product catalog, shipping.

### Entities

#### Customer

| Field | Type | Rules |
|---|---|---|
| `id` | UUID | generated |
| `name` | string | required, `min_length=1` |
| `tax_id` | string | required, **unique**, pattern `^[A-Za-z0-9./-]{5,20}$` |
| `passport_number` | string | optional, **unique** when present, ICAO pattern `^[A-Z0-9]{6,9}$` |
| `email` | string | required, validated via `EmailStr` (Pydantic) |
| `deleted_at` | datetime | soft-delete (null = active) |

- `tax_id`, `passport_number` and `email` are PII — never logged in plaintext
  (`mask_sensitive()`, see `api/utils/sensitive.py`).

#### Order (aggregate root)

| Field | Type | Rules |
|---|---|---|
| `id` | UUID | generated |
| `customer_id` | UUID | required, must reference an existing customer (`VALIDATION-07`) |
| `items` | list of Item | composition — lifecycle tied to the Order, max. `MAX_ITEMS_PER_ORDER` (200) |
| `total` | decimal | **derived**, recalculated on every item mutation |
| `status` | `OrderStatus` enum | `OPEN → CONFIRMED → CANCELED`, default `OPEN` |
| `version` | integer | optimistic concurrency control (SQLAlchemy `StaleDataError` → `CONFLICT-00`) |

- `confirm()` is only allowed from `OPEN` and requires at least 1 item; fails with
  `VALIDATION-04` (invalid status) or `VALIDATION-03` (no items).
- `cancel()` is allowed from any status except `CANCELED` (`VALIDATION-08`).
- While `OPEN`, items can be added/removed freely (`is_editable`); otherwise,
  `VALIDATION-02`.

#### Item (child of Order)

| Field | Type | Rules |
|---|---|---|
| `id` | UUID | generated |
| `order_id` | UUID | required |
| `description` | string | required, non-blank, `max_length=255` |
| `unit_price` | decimal | required, positive (`gt=0`), max. 2 decimal places |
| `quantity` | integer | required, positive (`gt=0`) |

- Item subtotal = `unit_price * quantity` (computed, not persisted).

### `OrderStatusChangedEvent` event

Fired at the end of `confirm()`/`cancel()`, only when the customer has a non-empty
`email`. Carries `order_id`, `customer_email`, `customer_name`, `old_status`,
`new_status`, `total_amount` and `changed_at`. Logged (structured log, email never in
plaintext) and published to RabbitMQ (`RABBITMQ_URL`) for asynchronous processing by
the worker (`worker.py`), which actually sends the email via SMTP (`SMTP_HOST`/
`SMTP_PORT`/`SMTP_FROM`, defaults to local Mailpit), rendered via Jinja2 from
`templates/email/order_status_changed.html`. A broker/SMTP failure never breaks the
HTTP request or the order's commit (see `api/events/rabbitmq_publisher.py`).

### Error catalog

**Validation (400)**
| Code | Description |
|---|---|
| `VALIDATION-01` | invalid request body (Pydantic schema) |
| `VALIDATION-02` | order not editable in its current status |
| `VALIDATION-03` | confirming an order with no items |
| `VALIDATION-04` | invalid status transition when confirming |
| `VALIDATION-05` | invalid filter value in search |
| `VALIDATION-06` | unknown sort field in search |
| `VALIDATION-07` | nonexistent customer when creating an order |
| `VALIDATION-08` | cancelling an already-cancelled order |

**Not found (404)**
| Code | Description |
|---|---|
| `RESOURCE-NOT-FOUND-01` | customer not found |
| `RESOURCE-NOT-FOUND-02` | order not found |
| `RESOURCE-NOT-FOUND-03` | item not found |

**Conflict (409)**
| Code | Description |
|---|---|
| `CONFLICT-00` | concurrent modification (`StaleDataError`, optimistic lock) |
| `CONFLICT-01` | duplicate `tax_id` |
| `CONFLICT-02` | duplicate `passport_number` |
| `CONFLICT-03` | deleting a customer with associated orders |

**Other**
| Code | Description |
|---|---|
| `INTERNAL-00` | unexpected, unhandled error |

## Endpoints

### `/orders` (requires an authenticated user)

| Method | Path | Description |
|---|---|---|
| POST | `/orders` | Create order |
| GET | `/orders/search` | Search orders (query params) |
| POST | `/orders/search` | Search orders (body) |
| GET | `/orders/{order_id}` | Get order by id |
| DELETE | `/orders/{order_id}` | Delete (soft) order |
| POST | `/orders/{order_id}/items` | Add item |
| PATCH | `/orders/{order_id}/items/{item_id}` | Update item quantity |
| DELETE | `/orders/{order_id}/items/{item_id}` | Remove item |
| POST | `/orders/{order_id}/confirm` | Confirm order |
| POST | `/orders/{order_id}/cancel` | Cancel order |

### `/customers` (mutations require `ROLE_ADMIN`; reads require an authenticated user)

| Method | Path | Description |
|---|---|---|
| POST | `/customers` | Create customer (admin) |
| GET | `/customers/search` | Search customers (query params) |
| POST | `/customers/search` | Search customers (body) |
| GET | `/customers/{customer_id}` | Get customer by id |
| PUT | `/customers/{customer_id}` | Update customer (admin) |
| DELETE | `/customers/{customer_id}` | Delete (soft) customer (admin) |

The full contract (request/response schemas) is always available in the OpenAPI spec
auto-generated by FastAPI: `/docs` (Swagger UI) and `/openapi.json`, disabled only
when `APP_ENV=production`.

## Running locally

Requires Postgres, RabbitMQ and Mailpit — `docker compose up -d` starts all three —,
plus the environment variables `DATABASE_URL`, `JWT_SECRET`, `JWT_AUDIENCE`,
`JWT_ISSUER`, `CORS_ALLOWED_ORIGINS` (required only when `APP_ENV=production`),
`RABBITMQ_URL` (default `amqp://guest:guest@localhost:5672/`) and `SMTP_HOST`/
`SMTP_PORT`/`SMTP_FROM` (default Mailpit: `localhost`/`1025`/
`no-reply@order-api.local`). Mailpit web UI to inspect received emails:
`http://localhost:8025`; RabbitMQ Management UI (guest/guest):
`http://localhost:15672`.

```
docker compose up -d
pip install -r requirements.txt
alembic upgrade head
uvicorn main:app --reload
python worker.py   # separate process: consumes order.status.changed
```

## Tests and quality

- `pytest tests/unit` — mocked, no database, runs in any environment.
- `pytest tests/integration` — real Postgres via Testcontainers, requires local Docker.

```
ruff check .
mypy api worker.py
bandit -r api main.py database.py worker.py
make verify   # single local gate: ruff → mypy → bandit → pytest with coverage
```

`make verify` reproduces `ci.yml` in a single local command. Minimum coverage is
`[tool.coverage.report] fail_under = 80` (`pyproject.toml`).
