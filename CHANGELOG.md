# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/). Este
projeto não versiona releases (`main` é deployado continuamente); as entradas abaixo
agrupam o histórico por tema, não por tag.

## [Unreleased]

### Security

- Testes de integração contra Postgres real e conexões concorrentes (`tests/integration/test_database_behavior.py`): recadastro do
  documento de cliente excluído, dois cadastros simultâneos do mesmo documento, corrida excluir cliente x criar pedido (10 rodadas),
  lock otimista e ciclo `upgrade head` / `check` / `downgrade base` / `upgrade head` das migrations.

- JWT: `JWT_AUDIENCE` e `JWT_ISSUER` são obrigatórios fora de development/test (o default igual ao nome do serviço permitiria
  reaproveitar um token entre serviços); tolerância de 30 s de relógio (`exp`/`nbf`); `sub` com no máximo 200 caracteres; a
  validação do token ficou num ponto só (`decode_access_token`), usado também pelo rate limit.
- Limite de corpo agora também conta os bytes de um upload em chunks, sem `Content-Length` (antes só o header era conferido e
  um corpo em chunks passava direto).
- Imagem Docker em dois estágios, só com as dependências de runtime (`requirements.txt`; ferramentas de teste e lint
  foram para `requirements-dev.txt`), base fixada por digest. Compose publica tudo em `127.0.0.1` e com imagens por
  digest. `ci.yml` e `codeql.yml` com `permissions: contents: read`.
- Broker e SMTP: fora de `development`/`test`, `RABBITMQ_URL` é obrigatória e tem que ser `amqps://` (sem fallback
  para `guest:guest`), `SMTP_STARTTLS=true` é obrigatório e credencial (`SMTP_USER`/`SMTP_PASSWORD`) nunca trafega
  sem TLS em nenhum ambiente. A API e o worker falham no boot se a configuração for insegura.
- Cada mensagem leva um `message_id` (mantido nos retries) e o worker ignora a reentrega de um id já enviado.
- Destinatário recusado pelo SMTP vai direto para a DLQ, sem retry e sem logar o endereço.
- Rate limit por usuário (`sub` do token verificado) e por endereço só para anônimos; escritas de pedido têm limite
  próprio (30/min); `/health` fora do limite global.
- `X-Request-Id` só é propagado se for UUID canônico (senão é substituído): fecha log forging.
- Recusas precoces (413, `Content-Length` inválido) agora passam por correlation id e security headers; um
  `Content-Length` não numérico é 400 em vez de 500.
- Entrada: `name` (200) e `email` (320) com tamanho máximo e nome em branco rejeitado; `unit_price` limitado ao que
  `Numeric(10, 2)` aceita (acima disso virava 500 no INSERT) e `quantity` a 10.000 por item.
- `tax_id` é gravado e comparado na forma canônica (maiúsculas, sem `.`/`-`/`/`), com no mínimo 5 letras ou dígitos:
  `"123.456-78"` e `"12345678"` deixam de ser dois cadastros do mesmo documento. Linhas já gravadas com pontuação ou
  minúsculas precisam de um `UPDATE` de normalização antes do deploy.
- `tax_id` e `passport_number` são únicos só entre clientes ativos (índice único parcial, migration `0002`): antes um
  cliente excluído mantinha o documento reservado e recadastrá-lo dava 500 (`IntegrityError` sem handler).
- `IntegrityError` vira 409 (`CONFLICT-01`/`CONFLICT-02`, ou `CONFLICT-04` genérico), sem ecoar o valor.
- Excluir cliente (`FOR UPDATE`) e criar pedido (`FOR SHARE`) serializam na linha do cliente: não sobra mais pedido
  ativo de cliente excluído.
- `POST /orders/{id}/items` respeita o limite de 200 itens (`VALIDATION-09`), antes só aplicado na criação.
- JWT: `exp`, `sub`, `aud` e `iss` agora são obrigatórios (antes um token sem `exp` valia para sempre); `roles`
  que não seja lista de strings é rejeitado (string viraria checagem de substring: `"admin" in "superadmin"`).
- 401 e 403 usam o mesmo corpo `{message, code, params, request_id}` dos demais erros (`AUTH-01`/`AUTH-02`), sem
  revelar o papel que faltou, e o 401 leva `WWW-Authenticate: Bearer`.
- Busca: `lk` trata `%` e `_` como literais; limites de campos, condições, itens de `in`,
  tamanho de valor e offset no `SearchRequest`.
- Os 409 de `tax_id` e `passport_number` não ecoam mais o valor (PII).
- Filtros tipados (`gt`/`lt`/`between` rejeitados em enum e bool, decimal sem NaN/Infinity/expoente): valores convertidos estritamente ao tipo da coluna (`bool`, `datetime`, `int`, `UUID`, enum);
  `between` exige dois valores, `lk` só em texto; antes `"false"` filtrava como `true`, filtro de data sempre dava 400 e
  `between` com um valor dava 500.

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

### Changed

- Gate de cobertura sobe de 80% (só statements) para 90%, agora medindo branch coverage
  também (`[tool.coverage.run] branch = true`) — cobertura real já estava em ~99% com
  branches contados; o número antigo só não refletia isso. Fechados os poucos gaps reais
  restantes: rollback em `get_db()`, token sem `sub`, filtro/sort por campo desconhecido em
  `paginate()`, validators de `ItemInput` (descrição em branco, mais de 2 casas decimais) e
  os endpoints `PUT /customers/{id}` e `GET`/`DELETE /orders/{id}`, que não tinham nenhum
  teste de integração próprio.

### Security

- JWT validado com chave pública RSA (`JWT_PUBLIC_KEY_PATH`, RS256) em vez de segredo HS256
  compartilhado — um vazamento não permite mais forjar token novo, só verificar os já
  emitidos (ver ADR 0004, que supersede a ADR 0003). Aplicação falha o startup
  (fail-closed) se `JWT_PUBLIC_KEY_PATH` estiver ausente, em qualquer ambiente.
- Schemas de request (`CustomerInput`, `ItemInput`, `ItemQuantityUpdate`, `OrderCreate`,
  `SearchRequest`) agora rejeitam campo desconhecido no body (`extra="forbid"`) em vez de
  ignorá-lo silenciosamente.
- `jinja2` atualizado para 3.1.6, corrigindo bypass de sandbox no filtro `|attr`
  ([GHSA-cpwx-vrp4-4pq7](https://github.com/pallets/jinja/security/advisories/GHSA-cpwx-vrp4-4pq7)).
- bandit (SAST) e CodeQL adicionados ao CI.
