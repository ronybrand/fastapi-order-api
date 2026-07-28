.PHONY: verify

# Gate de qualidade local: hard-fail em qualquer violacao de lint/tipo/seguranca ou
# cobertura abaixo do minimo (pyproject.toml).
verify:
	ruff check .
	mypy api worker.py
	bandit -r api main.py database.py worker.py
	pytest tests/unit tests/integration --cov=api --cov-report=term-missing
