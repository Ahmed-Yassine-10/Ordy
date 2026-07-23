# Ordy Celery worker image. Build context is the repo root.
FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app

COPY pyproject.toml uv.lock* ./
COPY libs/ordy-core/pyproject.toml libs/ordy-core/
COPY libs/ordy-ingest/pyproject.toml libs/ordy-ingest/
COPY services/workers/pyproject.toml services/workers/

RUN uv sync --package ordy-workers --no-dev --frozen || uv sync --package ordy-workers --no-dev

COPY libs/ libs/
COPY services/workers/ services/workers/

# Chromium for the Playwright website crawler (doc 04 §2.2).
RUN uv run playwright install --with-deps chromium || echo "playwright browser install deferred"

ENV PATH="/app/.venv/bin:${PATH}"
CMD ["celery", "-A", "ordy_workers.celery_app.celery_app", "worker", "--loglevel=INFO", "-Q", "ingestion,embeddings,webhooks"]
