# Ordy API image. Build context is the repo root.
FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# uv for fast, reproducible installs from the workspace lockfile.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy workspace manifests first for layer caching.
COPY pyproject.toml uv.lock* ./
COPY libs/ordy-core/pyproject.toml libs/ordy-core/
COPY libs/ordy-security/pyproject.toml libs/ordy-security/
COPY services/api/pyproject.toml services/api/

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
