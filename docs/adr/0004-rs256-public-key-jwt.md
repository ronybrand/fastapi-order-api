# ADR 0004: Validate JWTs against a local RSA public key, not a shared HS256 secret

## Status
Accepted

## Context
[ADR 0003](./0003-hs256-shared-secret-jwt.md) accepted HS256 with a shared secret
(`JWT_SECRET`) as a deliberate trade-off: simpler to wire than `nest-order-api`'s RS256
public-key-only approach, at the cost of this service being able to *mint* tokens for itself
(not just verify them) if `JWT_SECRET` ever leaked. A red-team-style review comparing the three
`order-api` ports flagged that trade-off as the most severe finding of the three implementations
specifically because it was the one closable at near-zero cost: `cryptography` (needed to generate/
handle RSA keys) is already a transitive dependency via `python-jose[cryptography]==3.5.0`, no new
package required.

## Decision
Replace `JWT_SECRET` (HS256) with `JWT_PUBLIC_KEY_PATH` (RS256, verify-only), mirroring
`nest-order-api`'s `JWT_PUBLIC_KEY_PATH`/`JwtStrategy` approach. There is still no `/auth/login` or
token-issuing endpoint in this repository - whatever issues tokens in a real deployment is expected
to sign with the *private* half of the key pair this service only ever holds the public half of.
The old fail-fast guard (refusing to boot outside `development`/`test` with the hardcoded default
secret) is gone entirely, not replaced with an equivalent: there is no "insecure default" to guard
against when the value is a public key path - an unset `JWT_PUBLIC_KEY_PATH` simply can't work in
any environment, and now fails for that reason (`RuntimeError` at import time) instead.

Tests (`tests/utils/jwt_keys.py`) generate a throwaway RSA key pair once per test session, write
the public half to a temp file, and use the private half to sign tokens
(`tests/utils/auth.py`) - no real key ever touches a committed file, and no Keycloak/OIDC
discovery is involved, same spirit as `nest-order-api`'s `JwtTestTokenFactory`.

## Alternatives considered
- **Keep HS256, only rotate `JWT_SECRET` more carefully / document rotation procedure**: doesn't
  change the underlying property that a leaked secret grants minting, not just verification - a
  process fix, not a design fix, for a design-level weakness that had a cheap design-level
  solution available.
- **Full OIDC discovery against a real Keycloak, mirroring `spring-order-api`**: still rejected for
  the same reason as in ADR 0003 - `spring-order-api` already demonstrates that setup once: a
  JVM-based Keycloak container, realm provisioning, JWKS discovery. Repeating it here adds
  operational weight without demonstrating anything new about FastAPI specifically.

## Consequences
- Positive: closes the "single point of compromise" gap ADR 0003 explicitly flagged as the
  trade-off's downside - a leaked `JWT_PUBLIC_KEY_PATH` value (or the file itself) grants an
  attacker nothing beyond what a public key legitimately allows: verifying tokens they could
  already verify by calling the API. It cannot be used to forge a new token.
- Positive: the fail-fast guard that existed only to catch one specific mistake (shipping the
  hardcoded HS256 default) is gone - there's simply no equivalent mistake shape with a public key.
- Neutral: still zero external identity dependency to start the app or run the test suite - the
  env var changed from a secret string to a file path, the operational simplicity ADR 0003 called
  out as HS256's advantage is unchanged.
- Negative accepted: same as `nest-order-api`'s ADR 0003 - no live demonstration of OIDC discovery,
  JWKS rotation, or Keycloak-specific realm/role provisioning in this project. That remains
  intentionally left to `spring-order-api`.
