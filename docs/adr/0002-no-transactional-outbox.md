# ADR 0002: Synchronous, in-request best-effort publish, not a transactional outbox

## Status
Accepted

## Context
`spring-order-api` (the Java reference implementation this project's domain is modeled after -
see `DOMAIN.md`) uses a transactional outbox: the status-changed event is written to an
`outbox_events` table in the same database transaction as the order update, and a separate poller
publishes it to RabbitMQ, guaranteeing the event is never lost even if the broker is down at
commit time.

This project does not have that guarantee, and dispatches more eagerly than even a typical
best-effort design: `OrderService.confirm()`/`cancel()` call
`publish_order_status_changed(build_order_status_changed_event(...))` synchronously, in-process,
directly in the request path, right after the order row is refreshed post-commit (see
`api/services/order_service.py`). `publish_to_rabbitmq` (`api/events/rabbitmq_publisher.py`)
catches any failure and only logs it - the HTTP response still returns success, but the
notification is silently dropped, with no outbox row to reprocess later.

## Decision
Keep the synchronous, best-effort publish rather than porting the outbox pattern or moving the
publish call off the request path.

## Alternatives considered
- **Port the transactional outbox from `spring-order-api`**: would require an `outbox_events`
  table + Alembic migration and a poller process claiming rows for publish. This is the
  architecturally correct choice for a system that cannot tolerate lost notifications, and is
  deliberately demonstrated once, well, in the reference implementation - porting it a second time
  to this FastAPI version would repeat the same lesson without adding new signal about FastAPI/
  SQLAlchemy idioms, which is the actual point of this port.
- **Move the publish call off the request path** (background task via `BackgroundTasks`, or a
  lightweight queue/worker handoff before responding): would stop a slow/unreachable broker from
  adding latency to the HTTP response, independent of the outbox question. Not done here - the
  failure mode this ADR is about (a dropped notification) is unchanged either way, and the current
  code keeps the entire event flow (build → publish → catch) in one traceable call instead of
  splitting timing concerns across two mechanisms.

## Consequences
- Positive: no extra table, no poller/worker claiming logic beyond the existing `worker.py`
  consumer - the publish path is one function call.
- Negative accepted: a RabbitMQ outage at the exact moment `confirm()`/`cancel()` runs loses that
  customer's status-change email permanently, with only a log line as a trace, and a slow broker
  adds directly to that request's latency since the call is synchronous. Acceptable here because
  this is a portfolio order-management API, not a system with a real SLA on notification delivery
  or request latency - the outbox pattern is already demonstrated where it matters
  (`spring-order-api`, its ADR 0006).
