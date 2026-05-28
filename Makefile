.PHONY: help up down logs backend frontend ingest db-shell redis-cli

SHELL := /bin/bash

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ─── Infrastructure ───────────────────────────────────────────────────────────

up: ## Start all Docker services (PostgreSQL, Redis, Milvus)
	docker compose up -d
	@echo "Waiting for services to be ready..."
	@sleep 5
	@echo "✅ Services started"

down: ## Stop all Docker services
	docker compose down

logs: ## Tail Docker service logs
	docker compose logs -f

restart: ## Restart all services
	docker compose restart

# ─── Backend ──────────────────────────────────────────────────────────────────

install-backend: ## Install Python dependencies
	cd backend && pip install -r requirements.txt

backend: ## Run FastAPI dev server (hot reload)
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

backend-check: ## Check backend syntax (no import errors)
	cd backend && python -c "from app.main import app; print('✅ Backend imports OK')"

# ─── Frontend ─────────────────────────────────────────────────────────────────

install-frontend: ## Install Node dependencies
	cd frontend && npm install

frontend: ## Run Vite dev server
	cd frontend && npm run dev

build-frontend: ## Build frontend for production
	cd frontend && npm run build

# ─── ETL / Data Ingestion ─────────────────────────────────────────────────────

seed-mock: ## Seed mock data (no StatsBomb needed, for local dev/testing)
	cd backend && python scripts/seed_mock.py

ingest: ## Run full ETL ingestion (requires STATSBOMB_DATA_PATH in .env)
	cd backend && python scripts/ingest.py

ingest-season: ## Ingest single season (use: make ingest-season COMPETITION_ID=2 SEASON_ID=44)
	cd backend && python scripts/ingest.py --competition_id $(COMPETITION_ID) --season_id $(SEASON_ID)

ingest-dry: ## Dry-run ETL (show what would be processed)
	cd backend && python scripts/ingest.py --dry-run

# ─── Database Utilities ───────────────────────────────────────────────────────

db-shell: ## Connect to PostgreSQL shell
	docker compose exec postgres psql -U $$(grep POSTGRES_USER docker-compose.yml | head -1 | cut -d= -f2) -d alofootmind

redis-cli: ## Open Redis CLI
	docker compose exec redis redis-cli

db-tables: ## List all PostgreSQL tables and row counts
	docker compose exec postgres psql -U postgres -d alofootmind -c "\
		SELECT relname AS table, n_live_tup AS rows \
		FROM pg_stat_user_tables \
		ORDER BY n_live_tup DESC;"

# ─── Setup ────────────────────────────────────────────────────────────────────

setup: ## First-time setup: copy .env.example and install deps
	@if [ ! -f backend/.env ]; then cp backend/.env.example backend/.env; echo "✅ Created backend/.env — please fill in your API keys"; fi
	$(MAKE) install-backend
	$(MAKE) install-frontend

dev: up ## Start infrastructure + both dev servers (runs in background)
	@echo "Starting backend..."
	@cd backend && uvicorn app.main:app --reload --port 8000 &
	@echo "Starting frontend..."
	@cd frontend && npm run dev

# ─── Production (Docker full-stack) ──────────────────────────────────────────

prod-build: ## Build backend + frontend Docker images
	docker compose --profile full build

prod-up: ## Start full production stack (infra + backend + frontend)
	docker compose --profile full up -d

prod-down: ## Stop full production stack
	docker compose --profile full down

prod-logs: ## Tail production logs
	docker compose --profile full logs -f backend frontend
