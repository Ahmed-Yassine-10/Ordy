# Ordy Celery worker image. Build context is the repo root.
FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app

# uv resolves the ENTIRE workspace on sync, so every member declared in
# [tool.uv.workspace] must have its pyproject.toml present before `uv sync`.
COPY pyproject.toml uv.lock* ./
COPY libs/ordy-core/pyproject.toml libs/ordy-core/
COPY libs/ordy-security/pyproject.toml libs/ordy-security/
COPY libs/ordy-ingest/pyproject.toml libs/ordy-ingest/
COPY libs/ordy-rag/pyproject.toml libs/ordy-rag/
COPY libs/ordy-tools/pyproject.toml libs/ordy-tools/
COPY libs/ordy-orders/pyproject.toml libs/ordy-orders/
COPY libs/ordy-automation/pyproject.toml libs/ordy-automation/
COPY libs/ordy-agent/pyproject.toml libs/ordy-agent/
COPY services/api/pyproject.toml services/api/
COPY services/workers/pyproject.toml services/workers/
COPY services/voice/pyproject.toml services/voice/
COPY services/automation/pyproject.toml services/automation/

RUN uv sync --package ordy-workers --no-dev --frozen || uv sync --package ordy-workers --no-dev

COPY libs/ libs/
COPY services/workers/ services/workers/

# Chromium for the Playwright website crawler (doc 04 §2.2).
RUN uv run playwright install --with-deps chromium || echo "playwright browser install deferred"

ENV PATH="/app/.venv/bin:${PATH}"
CMD ["celery", "-A", "ordy_workers.celery_app.celery_app", "worker", "--loglevel=INFO", "-Q", "ingestion,embeddings,webhooks"]
