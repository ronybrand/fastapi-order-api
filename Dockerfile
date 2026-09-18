# syntax=docker/dockerfile:1

# Single stage: requirements.txt mixes runtime and dev/lint/test tooling (ruff, mypy, bandit,
# pytest, testcontainers) in one file - there's no separate requirements-prod.txt in this
# project, so splitting the build here would introduce a dependency-management convention the
# rest of the repo doesn't have, just to shave image size. Tests/lint are not run in this build:
# CI (.github/workflows/ci.yml) already runs them on every push/PR.
FROM python:3.12-slim
RUN addgroup --system app && adduser --system --ingroup app app
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py database.py worker.py ./
COPY api/ api/
COPY alembic/ alembic/
COPY alembic.ini .
COPY templates/ templates/
USER app

# Same image runs both the API and worker.py (the RabbitMQ notification consumer, see
# ADR 0002) - only the command differs, e.g. `docker run <image> python worker.py`.
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
