.PHONY: up down restart logs logs-be logs-db logs-xml \
        shell-be shell-db shell-xml migrate migrate-new migrate-down \
        seed test test-v test-file lint format typecheck \
        build-prod up-prod help

# ── Development stack ─────────────────────────────────────────────────────────

up:  ## Start all services in background (build if needed)
	@echo "▶ Starting Aracne2 development stack..."
	@docker compose up -d --build

down:  ## Stop and remove containers (volumes are preserved)
	@echo "▶ Stopping Aracne2 stack..."
	@docker compose down

restart:  ## down + up
	@$(MAKE) down
	@$(MAKE) up

logs:  ## Follow logs for all services
	@docker compose logs -f

logs-be:  ## Follow backend logs only
	@docker compose logs -f backend

logs-db:  ## Follow postgres logs only
	@docker compose logs -f postgres

logs-xml:  ## Follow existdb logs only
	@docker compose logs -f existdb

# ── Shell access ──────────────────────────────────────────────────────────────

shell-be:  ## Open bash in the backend container
	@docker compose exec backend bash

shell-db:  ## Open psql in the postgres container
	@docker compose exec postgres psql -U $${POSTGRES_USER:-aracne2} -d $${POSTGRES_DB:-aracne2}

shell-xml:  ## Print eXist-db dashboard URL
	@echo "eXist-db dashboard: http://localhost:8080/exist/apps/dashboard"

# ── Database migrations ───────────────────────────────────────────────────────

migrate:  ## Run alembic upgrade head in the backend container
	@echo "▶ Running database migrations..."
	@docker compose exec backend alembic upgrade head

migrate-new:  ## Create new migration (MSG="description" required)
	@test -n "$(MSG)" || (echo "Error: MSG is required. Usage: make migrate-new MSG=\"your description\"" && exit 1)
	@echo "▶ Creating migration: $(MSG)"
	@docker compose exec backend alembic revision --autogenerate -m "$(MSG)"

migrate-down:  ## Run alembic downgrade -1
	@echo "▶ Rolling back last migration..."
	@docker compose exec backend alembic downgrade -1

# ── Seed ──────────────────────────────────────────────────────────────────────

seed:  ## Run seed.py in the backend container (idempotent)
	@echo "▶ Seeding initial data..."
	@docker compose exec backend python -m app.db.seed

# ── Tests ─────────────────────────────────────────────────────────────────────

test:  ## Run pytest with coverage in the backend container
	@echo "▶ Running tests..."
	@docker compose exec backend pytest --cov=app --cov-report=term-missing

test-v:  ## pytest -v --tb=short
	@echo "▶ Running tests (verbose)..."
	@docker compose exec backend pytest -v --tb=short

test-file:  ## pytest on a specific file (FILE=path/to/test.py)
	@test -n "$(FILE)" || (echo "Error: FILE is required. Usage: make test-file FILE=app/tests/test_auth.py" && exit 1)
	@echo "▶ Running tests in $(FILE)..."
	@docker compose exec backend pytest $(FILE) -v --tb=short

# ── Code quality ──────────────────────────────────────────────────────────────

lint:  ## ruff check + mypy in the backend container
	@echo "▶ Running ruff check..."
	@docker compose exec backend ruff check app
	@echo "▶ Running mypy..."
	@docker compose exec backend mypy app

format:  ## ruff format in the backend container
	@echo "▶ Running ruff format..."
	@docker compose exec backend ruff format app

typecheck:  ## mypy --strict in the backend container
	@echo "▶ Running mypy --strict..."
	@docker compose exec backend mypy --strict app

# ── Production ────────────────────────────────────────────────────────────────

build-prod:  ## Build production images
	@echo "▶ Building production images..."
	@docker compose -f docker-compose.yml -f docker-compose.prod.yml build

up-prod:  ## Start production stack
	@echo "▶ Starting Aracne2 production stack..."
	@docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# ── Help ──────────────────────────────────────────────────────────────────────

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
