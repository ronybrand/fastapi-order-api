# ADR 0003: Validate JWTs with a shared HS256 secret, not OIDC discovery against Keycloak

## Status
Accepted

## Context
`spring-order-api` runs a real Keycloak and does OIDC discovery against it
(`JwtDecoders.fromIssuerLocation(issuerUri)`); `nest-order-api` validates against a static RSA
*public* key file (asymmetric, verify-only - see that project's ADR 0003). This project does
neither: `api/dependencies/dependencies.py` decodes tokens with `python-jose` using a single
symmetric secret (`JWT_SECRET`, HS256) read from an environment variable, with a fail-fast guard
that refuses to start outside `development`/`test` if that variable is still the hardcoded
insecure default. There is no `/auth/login` or token-issuing endpoint in this repository - whatever
issues tokens in a real deployment is expected to sign with the same `JWT_SECRET`, out of band.

## Decision
Keep HS256 with a shared secret rather than switching to RS256 or adding OIDC discovery.

## Alternatives considered
- **Run Keycloak here too, mirroring `spring-order-api`**: `spring-order-api` already demonstrates
  wiring a real identity provider with OIDC discovery once - repeating that setup in this port
  would add the same operational weight (a JVM-based Keycloak container) without demonstrating
  anything new about FastAPI specifically.
- **RS256 with a public-key-only verifier, mirroring `nest-order-api`**: would mean this API only
  ever holds the public half of the signing key, which is the better-isolated design (compromising
  this service's config can't be used to *mint* tokens, only verify them) - already demonstrated in
  the NestJS port. HS256 here intentionally shows the other end of that trade-off: simpler to wire
  (one secret, no key-pair generation/rotation story), at the cost of this service being able to
  forge tokens for itself if `JWT_SECRET` leaked - acceptable given there is no untrusted code
  running inside this service that could exploit that, and the fail-fast guard above already
  prevents the weakest version of this mistake (shipping the default secret to a real environment).

## Consequences
- Positive: zero external identity dependency to start the app or run the test suite - one env var.
- Negative accepted: `JWT_SECRET` is a single point of compromise that grants both minting and
  verification, unlike the RS256 (`nest-order-api`) or OIDC (`spring-order-api`) approaches this
  portfolio also demonstrates. Rotation means every party holding the secret must be updated in
  lockstep, with no overlap window - acceptable for a single-service, single-issuer setup with no
  live deployment.
