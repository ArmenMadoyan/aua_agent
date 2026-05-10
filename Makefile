.PHONY: help install run-backend run-frontend run migrate docker-up docker-down docker-build lint clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ─── Local development ───────────────────────────────────────

install: ## Install Python dependencies
	pip install -r requirements.txt

run-backend: ## Start FastAPI backend (dev, with reload)
	uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000

run-frontend: ## Start Streamlit frontend
	streamlit run frontend/app.py

run: ## Start both backend and frontend (background backend)
	@echo "Starting backend on :8000 ..."
	uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000 &
	@echo "Starting frontend on :8501 ..."
	streamlit run frontend/app.py

migrate: ## Run Alembic migrations
	alembic upgrade head

# ─── Docker ──────────────────────────────────────────────────

docker-build: ## Build Docker images
	docker compose build

docker-up: ## Start all services (db + backend + frontend)
	docker compose up -d

docker-down: ## Stop all services
	docker compose down

docker-logs: ## Tail logs from all services
	docker compose logs -f

docker-reset: ## Stop services and remove volumes (fresh start)
	docker compose down -v

# ─── Quality ─────────────────────────────────────────────────

lint: ## Run ruff linter (install ruff first: pip install ruff)
	ruff check .

format: ## Auto-format with ruff
	ruff format .

# ─── Cleanup ─────────────────────────────────────────────────

clean: ## Remove __pycache__, .pyc, and other temp files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
