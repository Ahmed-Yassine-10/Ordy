# Ordy API image. Build context is the repo root.
FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# uv for fast, reproducible installs from the workspace lockfile.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy workspace manifests first for layer caching. uv resolves the ENTIRE workspace on
# sync, so every member declared in [tool.uv.workspace] must have its pyproject.toml
# present here — a missing one aborts the sync before any source is copied.
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

# Install the api project + its workspace deps.
RUN uv sync --package ordy-api --no-dev --frozen || uv sync --package ordy-api --no-dev

# Now copy sources.
COPY libs/ libs/
COPY services/api/ services/api/

# Non-root runtime user.
RUN useradd --create-home --uid 10001 ordy
USER ordy

ENV PATH="/app/.venv/bin:${PATH}"
EXPOSE 8000
CMD ["uvicorn", "ordy_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
