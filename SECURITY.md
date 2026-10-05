# Security Policy

## Supported versions

This is a single-branch portfolio project (no maintained release lines) - security fixes land on
`main` only. There is no LTS/backport policy.

## Reporting a vulnerability

Please **do not** open a public GitHub issue for a suspected vulnerability. Instead, use
[GitHub's private vulnerability reporting](../../security/advisories/new) for this repository
(Security tab → "Report a vulnerability"), or contact the maintainer directly via the email on
the [GitHub profile](https://github.com/ronybrand).

Include, where applicable:

- A description of the vulnerability and its potential impact.
- Steps to reproduce (a minimal request/payload is ideal).
- The affected endpoint(s) or component(s).

This project is maintained on a best-effort basis (no SLA), but reports are taken seriously and
triaged as soon as possible.

## Scope

In scope: the application code in this repository (`api/`), the `worker.py` notification
process, and the Dockerfile/CI workflows that build and ship them.

Out of scope: the third-party services this project integrates with when self-hosted for local
development (PostgreSQL, RabbitMQ) - report issues in those projects upstream. Dependency
vulnerabilities are tracked automatically via Dependabot and CodeQL (see badges in
[README.md](README.md)) rather than manual reports.

## What this project already does

- Automated dependency updates via Dependabot, auto-merged after CI passes.
- Static analysis on every push/PR via [CodeQL](.github/workflows/codeql.yml), plus `ruff`,
  `mypy` and `bandit` enforced in CI.
- No production secrets committed to the repository - configuration is via environment variables,
  with local-dev-only defaults backed by `docker-compose.yml`.
- JWT authentication and rate limiting (`SlowAPIMiddleware`) on all endpoints.
- PII fields are masked via `api/utils/sensitive.py`, covered by its own test suite
  (`tests/unit/test_sensitive.py`).
