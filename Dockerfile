# syntax=docker/dockerfile:1

# Two stages: the dependencies are resolved in a throwaway build stage and only the installed packages are
# copied into the runtime image - which holds the API and the worker.py consumer (same image, different
# command, see ADR 0002) but none of the pip cache, build leftovers or the test/lint tooling (that lives in
# requirements-dev.txt, installed only by CI). Tests/lint are not run here: CI already runs them.
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 AS build
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN addgroup --system app && adduser --system --ingroup app app
WORKDIR /app

COPY --from=build /install /usr/local
COPY main.py database.py worker.py ./
COPY api/ api/
COPY alembic/ alembic/
COPY alembic.ini .
COPY templates/ templates/
USER app

# No HEALTHCHECK on purpose: the same image runs the worker, which has no HTTP port. Probe GET /health on
# the API container from the orchestrator instead.
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
