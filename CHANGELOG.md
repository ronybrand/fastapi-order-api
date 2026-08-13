# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/). Este
projeto não versiona releases (`main` é deployado continuamente); as entradas abaixo
agrupam o histórico por tema, não por tag.

## [Unreleased]

### Added

- Domínio `Customer`/`Order`/`Item` completo: models, schemas, services, routers, migration
  inicial.
- Autenticação JWT, `require_role`, middlewares de segurança (CSP/HSTS, limite de tamanho de
  body, correlation id).
- Notificação assíncrona de mudança de status via RabbitMQ + worker dedicado (`worker.py`),
  e-mail renderizado em HTML (Jinja2) e enviado via SMTP.
- Pipeline de CI completo: lint (ruff), type-check (mypy), SAST (bandit), testes
  unit+integration com gate de cobertura, verificação de drift de migration
  (`alembic check`) e CodeQL — todos rodando em todo PR.
- Dependabot (pip + GitHub Actions) mantendo dependências atualizadas automaticamente.
- Testes unitários (mockado) e de integração (Testcontainers Postgres) cobrindo services,
  routers, middlewares, paginação/busca, mascaramento de PII e o fluxo de notificação
  RabbitMQ/SMTP.
- Catálogo de erros, endpoints e regras de domínio documentados no README.

### Changed

- `OrderStatus`/`FilterOperator` migrados de `str, Enum` para `enum.StrEnum`;
  `PaginatedResponse` migrado para sintaxe de generics PEP 695 (`class X[T]`).
- Diversas dependências atualizadas via Dependabot (fastapi, sqlalchemy, pydantic,
  python-jose, pytest-cov, testcontainers, alembic, ruff, mypy, actions/checkout,
  actions/setup-python, codeql-action).

### Fixed

- Modelo `Order.customer_id`/`Item.order_id` estava sem os índices e o `ondelete=CASCADE`
  já presentes na migration — divergência encontrada via `alembic check`.
- Eager loading de itens na busca de orders, evitando N+1 queries.
- Múltiplas condições de filtro no mesmo campo agora combinadas com AND (antes,
  sobrescreviam-se).
- Rotas estáticas `/search` deixaram de ser sombreadas por `/{id}` nos routers de order e
  customer.
- Código de erro distinto para "cancelar order já cancelada" (evita reuso de código com
  significado diferente).
- Migration inicial não duplica mais o tipo ENUM `order_status` em upgrades repetidos.
- Filtro de `request_id` nos logs agora aplicado também a registros propagados de loggers
  filhos (bibliotecas de terceiros).
- Conexão dos testes de integração com Testcontainers forçada para IPv4 (instabilidade de
  ambiente).
- `DeprecationWarning`s surgidas após bump de dependências (`testcontainers.postgres` →
  `testcontainers.community.postgres`; `httpx` → `httpx2` usado pelo `starlette.testclient`).
- Handler global para exceções não tratadas: loga stack trace com `request_id`, devolve só
  `{"code": "INTERNAL-00"}` ao client, sem vazar detalhes internos.

### Security

- Aplicação falha o startup (fail-closed) se `APP_ENV`/`JWT_SECRET` estiverem ausentes ou
  com o valor default fora de `development`/`test`.
- `jinja2` atualizado para 3.1.6, corrigindo bypass de sandbox no filtro `|attr`
  ([GHSA-cpwx-vrp4-4pq7](https://github.com/pallets/jinja/security/advisories/GHSA-cpwx-vrp4-4pq7)).
- bandit (SAST) e CodeQL adicionados ao CI.
