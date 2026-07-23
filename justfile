# Ordy task runner.  Install just: https://github.com/casey/just
set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

# List recipes
default:
    @just --list

# Bring up the local stack (Postgres, Redis, MinIO, api)
dev:
    docker compose up --build

# Stop and remove the stack
down:
    docker compose down

# Run database migrations (uses the migrator role)
migrate:
    cd services/api && uv run alembic upgrade head

# Create a new migration from model changes
makemigration name:
    cd services/api && uv run alembic revision --autogenerate -m "{{name}}"

# Seed the demo restaurant (Pizza Rustica Sfax)
seed:
    cd services/api && uv run python -m ordy_api.scripts.seed_demo

# Run the API locally (expects .env + running Postgres/Redis)
api:
    cd services/api && uv run uvicorn ordy_api.main:app --reload --port 8000

# Regenerate the TypeScript SDK from the live OpenAPI spec
gen-sdk:
    cd apps/web && pnpm run gen:sdk

# Lint + typecheck + test everything
check:
    uv run ruff check .
    uv run mypy libs services
    uv run pytest -q

# Frontend dev server
web:
    cd apps/web && pnpm dev
