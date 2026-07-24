# Ordy automation sandbox (doc 08 §5). Highest-risk component: it executes against
# arbitrary third-party sites, so it runs non-root with a read-only root filesystem and
# no database credentials. Network egress is restricted by the Kubernetes NetworkPolicy
# (allowlist = the approved target domain only), not by this image.
FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy AS base

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app

COPY pyproject.toml uv.lock* ./
COPY libs/ordy-core/pyproject.toml libs/ordy-core/
COPY libs/ordy-automation/pyproject.toml libs/ordy-automation/
COPY services/automation/pyproject.toml services/automation/

RUN uv sync --package ordy-sandbox --no-dev --frozen || uv sync --package ordy-sandbox --no-dev

COPY libs/ libs/
COPY services/automation/ services/automation/

# Non-root. The runtime mounts a tmpfs at /tmp for scratch; nothing persists.
RUN useradd --create-home --uid 10001 sandbox && chown -R sandbox:sandbox /app
USER sandbox

ENV PATH="/app/.venv/bin:${PATH}" \
    HOME=/home/sandbox \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Hard wall-clock ceiling per run is enforced by the caller; this is a backstop.
CMD ["python", "-c", "import ordy_sandbox; print('ordy sandbox ready', ordy_sandbox.__version__)"]
