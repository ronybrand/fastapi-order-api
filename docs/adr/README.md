# Architecture Decision Records

Log of the non-obvious technical decisions made in this project — context, what was decided,
alternatives discarded, and consequences (including the ones left deliberately unmitigated).

- [0001 — Binary RBAC (authenticated user vs admin), not per-resource permissions](0001-binary-rbac-admin-user.md)
- [0002 — Synchronous, in-request best-effort publish, not a transactional outbox](0002-no-transactional-outbox.md)
- [0003 — Validate JWTs with a shared HS256 secret, not OIDC discovery against Keycloak](0003-hs256-shared-secret-jwt.md)
