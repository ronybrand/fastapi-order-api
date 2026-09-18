# ADR 0001: Binary RBAC (authenticated user vs admin), not per-resource permissions

## Status
Accepted

## Context
`customers.py`/`orders.py` routers need to tell apart who can read data from who can mutate it.
The domain (see `README.md`'s entity tables) has no concept of ownership or tenancy - it's an
internal order-management API, not a customer-facing self-service one where a caller could be
restricted to their own records.

## Decision
Two roles only, read from the `roles` claim of the JWT (`api/dependencies/dependencies.py`,
`get_current_user`): any authenticated caller (`ROLE_USER`, the default when the claim is absent)
can call every `GET` route; `ROLE_ADMIN` is additionally required for every mutating route, via the
`require_role(ROLE_ADMIN)` dependency factory (e.g. `customers.py`'s `create_customer`). The
factory's own docstring already states this is the project's current authorization granularity and
that a new, narrower domain role should not be introduced without that decision being made
explicitly (see the `fastapi-feature` skill, "Autenticação e Autorização").

## Alternatives considered
- **Per-resource/ownership-based authorization**: doesn't map to the actual domain - there's no
  notion of a customer being the same principal as an API caller placing/managing their own order.
- **A single role (any authenticated caller can do anything)**: simpler, but throws away the
  ability to exercise a read-vs-write authorization boundary, which is exactly the kind of
  access-control granularity a backend-focused portfolio piece should demonstrate.
- **Fine-grained permissions (e.g. `orders:write`, `customers:delete`)**: proportional to a
  multi-team/multi-client API where different callers need different slices of the same resource.
  This API has exactly two kinds of caller in practice - two roles already capture that
  distinction without inventing a permission model nothing in the domain asks for.

## Consequences
- Positive: authorization logic stays in one dependency factory, reused identically by both
  routers - easy to audit by grep'ing for `require_role`.
- Negative accepted: adding a third kind of caller (e.g. a read-only auditor role) later means
  touching every mutating route's `Depends(require_role(...))` one by one - there's no role
  hierarchy or inheritance. Acceptable given the API's actual number of distinct callers today is
  two.
