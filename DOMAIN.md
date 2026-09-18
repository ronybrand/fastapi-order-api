# Domain: Order Management

Specification of the domain implemented in this repository: business rules, entities, events and
error contract, as the source of truth independent of implementation detail. Same domain as
[`spring-order-api`](https://github.com/ronybrand/spring-order-api) (the reference implementation)
and [`nest-order-api`](https://github.com/ronybrand/nest-order-api), ported to FastAPI + SQLAlchemy
+ PostgreSQL — see the README for stack-specific detail.

## 1. Overview

Simple order management domain with two aggregates:

```
Customer (1) ──< Order (1) ──< Item
```

- **Customer**: customer registration data.
- **Order** (aggregate root): a customer's order, with a list of items and a calculated total.
- **Item**: order line (free-text description, no product catalog).

Out of scope: payment, inventory, product catalog, shipping/freight.

## 2. Entities

### Customer

| Field | Type | Rules |
|---|---|---|
| `id` | UUID | generated |
| `name` | string | required, `min_length=1` |
| `tax_id` | string | required, **unique**, pattern `^[A-Za-z0-9./-]{5,20}$` |
| `passport_number` | string | optional, **unique** when present, ICAO pattern `^[A-Z0-9]{6,9}$` |
| `email` | string | required, validated via `EmailStr` (Pydantic) |
| `created_at`, `updated_at` | datetime | audit |
| `created_by`, `updated_by` | string | audit (user or "system") |
| `deleted_at`, `deleted_by` | datetime / string | soft-delete (null = active) |

- Identity equality by `tax_id` (careful: mutable field — don't rely on it as a stable collection
  key after updates).
- `tax_id`, `passport_number` and `email` are considered sensitive data (PII) — never logged in
  plaintext (`mask_sensitive()`).

### Order (aggregate root)

| Field | Type | Rules |
|---|---|---|
| `id` | UUID | generated |
| `customer_id` | UUID | required, must reference an existing customer |
| `items` | list of Item | composition — lifecycle tied to the Order, max. `MAX_ITEMS_PER_ORDER` (200) |
| `total` | decimal | **derived**, recalculated on every item mutation |
| `status` | enum `OrderStatus` | default `OPEN` |
| `version` | integer | optimistic concurrency control (SQLAlchemy `StaleDataError` on conflict) |
| `created_at`, `updated_at`, `created_by`, `updated_by` | — | audit |
| `deleted_at`, `deleted_by` | — | soft-delete |

- Identity equality by `id`.
- **Optimistic concurrency**: every write that changes `status` or `items` must check/increment
  `version`; a concurrent conflict is reported as a conflict error (HTTP 409 equivalent,
  `CONFLICT-00`).

### Item (child of Order)

| Field | Type | Rules |
|---|---|---|
| `id` | UUID | generated |
| `order_id` | UUID | required |
| `description` | string | required, non-blank, max. 255 chars |
| `unit_price` | decimal | required, positive (`gt=0`), max. 2 decimal places |
| `quantity` | integer | required, positive (`gt=0`) |

- Identity equality by `id` (not by description — descriptions can repeat within the same order).
- Item subtotal = `unit_price * quantity` (computed, not persisted).

## 3. OrderStatus enum

```
OPEN → CONFIRMED → CANCELED
OPEN → CANCELED
```

- `OPEN`: initial state. Items can be added/changed/removed. Can transition to `CONFIRMED` or
  `CANCELED`.
- `CONFIRMED`: items frozen (not editable). Can only transition to `CANCELED`.
- `CANCELED`: terminal state. No further transitions allowed.

## 4. Business rules / invariants

1. **Total calculation**: `order.total = Σ (item.unit_price × item.quantity)` over all current
   items. Recalculated after any item creation/update/removal.
2. **Items editable only while order is `OPEN`**: adding, changing the quantity of, or removing an
   item on a `CONFIRMED`/`CANCELED` order is a validation error (`VALIDATION-02`).
3. **Confirm order** (`OPEN → CONFIRMED`): fails if the current status isn't `OPEN`
   (`VALIDATION-04`), or if the order has no items (`VALIDATION-03`).
4. **Cancel order** (`OPEN|CONFIRMED → CANCELED`): fails if the current status is already
   `CANCELED` (`VALIDATION-08`).
5. **Create order**: requires an existing `customer_id` (`VALIDATION-07` if not found); builds the
   items from the request; computes the initial total.
6. **Item limit**: maximum of 200 items per order on creation.
7. **Customer uniqueness**: `tax_id` unique (`CONFLICT-01`); `passport_number` unique when provided
   (`CONFLICT-02`) — blank/absent doesn't count toward the check.
8. **Customer deletion blocked**: a customer with any non-deleted order cannot be deleted
   (`CONFLICT-03`) — soft-deleted orders don't count.
9. **Delete is always soft-delete**: on both aggregates — never a physical removal; records with
   `deleted_at` set are excluded from every default query.
10. **Optimistic concurrency on Order**: conflicting concurrent mutations fail with a conflict
    error (`CONFLICT-00`), they don't silently overwrite each other.

## 5. Domain events

### OrderStatusChangedEvent

Fired at the end of `confirm()`/`cancel()`, only when the customer has a non-empty email.

| Field | Type |
|---|---|
| `order_id` | UUID |
| `customer_email` | string |
| `customer_name` | string |
| `old_status` | OrderStatus |
| `new_status` | OrderStatus |
| `total_amount` | decimal |
| `changed_at` | datetime |

Published synchronously, in-process, directly in the request path right after the status
transition commits (see [ADR 0002](./docs/adr/0002-no-transactional-outbox.md) for why this is a
best-effort publish, not a transactional outbox). A separate `worker.py` process consumes the
RabbitMQ queue and sends the email via SMTP (Jinja2-rendered), retrying transient failures with a
fixed backoff before routing to the dead-letter queue — see the README's notification flow diagram
for the full picture.

## 6. Domain errors (reference catalog)

Categories and codes — see the README's "Error catalog" for the authoritative, versioned table;
summarized here for the domain-spec view:

**Validation (400)**: invalid request body, order not editable, confirming an empty order, invalid
status transition, invalid search filter/sort value, nonexistent customer on order creation,
cancelling an already-cancelled order.

**Not found (404)**: customer, order, item not found.

**Conflict (409)**: concurrent modification (optimistic lock), duplicate `tax_id`, duplicate
`passport_number`, deleting a customer with associated orders.

**Rate limit (429)**: too many requests (global or per-route limit exceeded).

**Other**: unexpected, unhandled error (500).

## 7. Use cases (application layer)

### Order
- `create(customer_id, items[])` → creates an `OPEN` order with the calculated total.
- `find_by_id(order_id)`
- `delete(order_id)` → soft-delete.
- `add_item(order_id, item)` → requires `OPEN`; recalculates the total.
- `update_item_quantity(order_id, item_id, quantity)` → requires `OPEN`; recalculates the total.
- `remove_item(order_id, item_id)` → requires `OPEN`; recalculates the total.
- `confirm(order_id)` → `OPEN → CONFIRMED`; requires non-empty items; publishes
  `OrderStatusChangedEvent`.
- `cancel(order_id)` → `OPEN|CONFIRMED → CANCELED`; publishes `OrderStatusChangedEvent`.
- `search(filters, sorting, pagination)`

### Customer
- `create(data)` → requires `ROLE_ADMIN`; validates `tax_id`/`passport_number` uniqueness.
- `update(id, data)` → requires `ROLE_ADMIN`; validates uniqueness excluding the record itself.
- `delete(id)` → requires `ROLE_ADMIN`; blocked if there are associated orders; soft-delete.
- `find_by_id(id)`
- `search(filters, sorting, pagination)`

## 8. Reference endpoints (this implementation's HTTP contract)

See the README's "Endpoints" section for the full, versioned table (methods, paths, role
requirements). Every mutating route on `/customers` requires `ROLE_ADMIN`; every route on `/orders`
and read routes on `/customers` require only an authenticated user. A missing/invalid token returns
`401`; a valid token without the required role returns `403`.

For search endpoints, filters/sorting/pagination follow the query-parameter or request-body shape
documented alongside each `search` route in the README.
