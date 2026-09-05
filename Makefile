# ARGUS - developer entry points.
#
# Every target works on a fresh clone with no accounts and no containers.
# `make help` lists them.

SHELL := /bin/bash
.DEFAULT_GOAL := help

VENV := .venv
ifeq ($(OS),Windows_NT)
	PY := $(VENV)/Scripts/python.exe
	PIP := $(VENV)/Scripts/python.exe -m pip
else
	PY := $(VENV)/bin/python
	PIP := $(VENV)/bin/python -m pip
endif

WEB := apps/web
API_HOST ?= 127.0.0.1
API_PORT ?= 8000

.PHONY: help
help: ## Show this help
	@echo "ARGUS - Agentic Risk Governance & Understanding System"
	@echo ""
	@echo "First run:"
	@echo "  make setup       install backend and frontend dependencies"
	@echo "  make seed-full   load the demo corpus and run an investigation"
	@echo "  make dev         start the API and the web app together"
	@echo ""
	@echo "All targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

.PHONY: setup
setup: venv install-web env ## Install everything needed to run locally
	@echo ""
	@echo "Setup complete. Next: make seed-full"

.PHONY: venv
venv: ## Create the Python virtualenv and install backend dependencies
	python -m venv $(VENV)
	$(PIP) install --upgrade pip --quiet
	$(PIP) install -r requirements-dev.txt

.PHONY: install-web
install-web: ## Install frontend dependencies
	cd $(WEB) && npm install --no-audit --no-fund

.PHONY: env
env: ## Create .env from the template if it does not exist
	@test -f .env || (cp .env.example .env && echo "Created .env from .env.example")

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

.PHONY: seed
seed: ## Load the demo corpus (documents, policies, case)
	$(PY) -m scripts.seed --reset

.PHONY: seed-full
seed-full: ## Load the corpus and run the investigation graph
	$(PY) -m scripts.seed --reset --investigate

.PHONY: migrate
migrate: ## Apply database migrations
	$(PY) -m alembic upgrade head

.PHONY: revision
revision: ## Generate a migration from model changes (m="message")
	$(PY) -m alembic revision --autogenerate -m "$(m)"

.PHONY: doctor
doctor: ## Report the resolved runtime configuration (no secrets shown)
	$(PY) -m scripts.doctor

.PHONY: record
record: ## Capture live model responses into data/recordings for Demo Mode
	$(PY) -m scripts.record_demo

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

.PHONY: api
api: ## Start the API on :8000
	$(PY) -m uvicorn argus_api.main:app --app-dir apps/api \
		--host $(API_HOST) --port $(API_PORT) --reload

.PHONY: web
web: ## Start the web app on :3000
	cd $(WEB) && npm run dev

.PHONY: dev
dev: ## Start API and web together
	@echo "API  -> http://$(API_HOST):$(API_PORT)/docs"
	@echo "Web  -> http://localhost:3000"
	@$(MAKE) -j2 api web

# ---------------------------------------------------------------------------
# Quality
# ---------------------------------------------------------------------------

.PHONY: test
test: ## Run the Python test suite
	$(PY) -m pytest

.PHONY: test-fast
test-fast: ## Run only the fast unit tests
	$(PY) -m pytest tests/unit -q

.PHONY: cov
cov: ## Run tests with a coverage report
	$(PY) -m pytest --cov --cov-report=term-missing

.PHONY: eval
eval: ## Run the evaluation suite
	$(PY) -m scripts.evaluate

.PHONY: eval-report
eval-report: ## Run the evaluation suite and write a JSON report
	$(PY) -m scripts.evaluate --json eval-report.json

.PHONY: lint
lint: ## Lint and type-check both applications
	$(PY) -m alembic check
	$(PY) -m ruff check ai apps scripts tests
	$(PY) -m ruff format --check ai apps scripts tests
	$(PY) -m mypy ai apps/api/argus_api
	cd $(WEB) && npm run lint && npm run typecheck

.PHONY: format
format: ## Auto-format both applications
	$(PY) -m ruff check ai apps scripts tests --fix
	$(PY) -m ruff format ai apps scripts tests
	cd $(WEB) && npm run format

.PHONY: build-web
build-web: ## Production build of the web app
	cd $(WEB) && npm run build

.PHONY: e2e
e2e: ## Run the Playwright end-to-end tests
	cd $(WEB) && npm run test:e2e

.PHONY: check
check: lint test eval build-web ## Everything CI runs

# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------

.PHONY: up
up: ## Start the full stack in Docker (Postgres + pgvector)
	docker compose up --build

.PHONY: down
down: ## Stop the Docker stack
	docker compose down

.PHONY: clean
clean: ## Remove build artefacts and the local database
	rm -rf $(WEB)/.next $(WEB)/node_modules/.cache .pytest_cache .ruff_cache .mypy_cache
	rm -f data/argus.db data/argus.db-wal data/argus.db-shm eval-report.json
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
