# Instruções para agentes de código neste repositório

Antes de editar qualquer arquivo em `api/`, invoque a skill `fastapi-feature`
(`.claude/skills/fastapi-feature/SKILL.md`), que contém as convenções completas de desenvolvimento
deste projeto.

A skill é a fonte de referência para arquitetura, implementação, testes, segurança e persistência.
Este arquivo contém apenas o checklist resumido dos pontos que devem ser validados antes de uma
alteração.

A instrução vale tanto para novas features quanto para correções, refatorações e auditorias de
código existente.

## Checklist antes de escrever código

- [ ] Li o domínio de referência mais parecido neste projeto e vou espelhar sua estrutura e convenções, evitando criar um padrão novo sem necessidade justificada.
- [ ] Classifiquei **cada campo novo** (model + schema de request) contra: PII (documento de identidade, e-mail, telefone, endereço...), categoria especial/LGPD art. 5º (saúde, biometria, dado racial/religioso/político), PCI (dado de cartão), dado financeiro (conta, salário, score), credenciais/segredos (senha, API key, token). Se o campo for sensível, utilize a infraestrutura existente (`info={"sensitive": True}`/`json_schema_extra={"sensitive": True}` + `mask_sensitive()`), nunca uma solução manual ad hoc. Nenhum campo sensível deve ser adicionado "para o caso de precisar depois" sem necessidade real da feature.
- [ ] Apliquei DRY (*Don't Repeat Yourself*) e eliminei duplicações de código, tanto em produção quanto nos testes.
- [ ] Avaliei se algum efeito colateral novo do service (envio de e-mail, notificação a outro serviço, geração de relatório) se beneficia de processamento assíncrono/mensageria (Celery/RQ com Redis, ou producer RabbitMQ/Kafka) versus resolver com uma chamada síncrona mais simples. Qualquer que seja a escolha, deixei o motivo explícito no PR/README, não uma decisão por padrão/hábito.

## TDD (red → green → refactor, não retroativo)

- [ ] Teste escrito e executado **falhando antes** do código de produção correspondente.
- [ ] `tests/unit/test_<dominio>_service.py` cobre todos os branches relevantes: caminho feliz, recurso inexistente, conflito de unicidade, regra de negócio violada e, quando aplicável, concorrência otimista (`version_id_col`).
- [ ] Todo domínio exposto via HTTP possui `tests/integration/test_<dominio>_integration.py` via Testcontainers, incluindo pelo menos um cenário de autorização negada (403) para cada endpoint protegido.
- [ ] Rate limiting, CORS ou qualquer outro guard de produção não foram alterados para facilitar testes; diferenças de configuração pertencem exclusivamente ao mecanismo de override de dependency do FastAPI.

## Entidade / persistência

- [ ] `id` gerado pelo banco (`server_default=text("gen_random_uuid()")`, tipo `postgresql.UUID`), nunca `default=uuid.uuid4` no model, salvo exceção documentada (volume alto/ordenação natural).
- [ ] Soft delete (`deleted_at`) como padrão quando a feature exigir histórico, com filtro manual `.filter(Model.deleted_at.is_(None))` em toda query de leitura do service — SQLAlchemy não aplica esse filtro automaticamente.
- [ ] `version_id_col` utilizado em entidades sujeitas a concorrência real; não é obrigatório em entidades de referência sem atualizações concorrentes relevantes.
- [ ] Toda validação de unicidade feita no service possui `UniqueConstraint` equivalente em `__table_args__`.
- [ ] `cascade="all, delete-orphan"` restrito a entidades-filho internas a um agregado, nunca entre duas entidades de domínio independentes.
- [ ] Múltiplas condições no mesmo `.filter(...)` são passadas como argumentos separados (nunca combinadas com o operador `and` do Python, que reduz silenciosamente ao segundo operando).

## Service / router / autorização

- [ ] Toda rota protegida declara `Depends(get_current_user)`/`Depends(require_role(...))` explícito; não existe rota pública por omissão.
- [ ] Recursos pertencentes a um usuário específico validam ownership na camada de service comparando `current_user.id` contra o campo de dono, tratando posse inválida como `CustomAPIException` 404, nunca 403.
- [ ] Novos códigos de erro seguem o padrão `<CATEGORIA>-NN` já usado no restante do arquivo; nunca reutilizar um código para um significado diferente.
- [ ] Router nunca lança exceção nem constrói resposta de erro diretamente — toda validação de negócio e `raise CustomAPIException(...)` acontece no service.
- [ ] Busca, filtro e paginação (quando existirem no domínio) reutilizam o helper compartilhado de `api/utils/pagination.py`; validação de campo/tipo é resolvida a partir de `sqlalchemy.inspect(model).columns`, evitando allowlist mantida manualmente por domínio.

## Baseline de segurança (não desativar por acidente)

- [ ] Security headers (`SecurityHeadersMiddleware`), rate limiting (`slowapi`), limite de tamanho de body, validação de `aud`/`iss` do JWT e o guard de CORS fail-fast em produção permanecem ativos; nenhuma dessas proteções foi desabilitada ou contornada para viabilizar uma implementação ou teste.
- [ ] `/docs`/`/redoc`/`/openapi.json` continuam desabilitados fora do ambiente de desenvolvimento.
- [ ] Segredos, chaves, tokens e connection strings nunca são commitados em código-fonte ou migrations; utilizar exclusivamente variável de ambiente/secret manager.
- [ ] Dados sensíveis nunca aparecem em `logging`/`print` em texto claro (incluindo payloads de erro de validação) e não são expostos num schema de resposta sem necessidade real. Campos marcados como sensíveis utilizam exclusivamente `mask_sensitive()`/`Field(exclude=True)`.

## Antes de considerar a mudança pronta

- [ ] `ruff check .` e `mypy api/` executados sem violações (gate real do build), com toda supressão (`# noqa`/`# type: ignore`) documentada com o motivo.
- [ ] Testes relevantes executados (`pytest <caminho>`), não apenas escritos.
- [ ] Falhas conhecidas da infraestrutura de testes (Docker/Testcontainers, ambiente local etc.) foram descartadas antes de concluir que existe um defeito na implementação.
- [ ] Toda migration nova foi revisada manualmente. `alembic revision --autogenerate` define apenas a estrutura; alterações em dados, índices, constraints e estratégia de rollback (`downgrade()` completo) foram validadas explicitamente.
- [ ] Nenhuma função/classe nova utilizada está deprecated na versão das dependências realmente resolvida em `requirements.txt`/`pyproject.toml`; havendo alternativa não deprecated, ela foi adotada em vez da API antiga.
- [ ] Checagens de nulo/vazio usam a forma positiva/direta (`is not None`/`is None` quando `0`/`False` são valores legítimos), nunca a negação do oposto nem duas condições manuais. Para regras de negócio sem checagem pronta, a condição foi extraída numa `@property` nomeada afirmativamente (ex. `is_cancelable`) em vez de negação (`not`) repetida nos pontos de uso.

O detalhamento completo de cada item (motivação, exceções válidas, decisões arquiteturais e exemplos) está documentado na skill `fastapi-feature`. Este arquivo é apenas um checklist operacional utilizado antes de considerar uma tarefa concluída.
