# NBA MoA Agents — common dev commands (local or CI).
# Requires: uv (https://docs.astral.sh/uv/), Node 20+, Docker for postgres/docker targets.

.PHONY: help install dev dev-frontend test test-backend test-integration lint format typecheck migrate docker-up docker-down eval

BACKEND := backend
FRONTEND := frontend
TEST_DATABASE_URL ?= postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/nba_test

help:
	@echo "Targets:"
	@echo "  install          Install backend (uv) and frontend (npm) dependencies"
	@echo "  dev              Start Postgres + backend on :8000 (run 'make dev-frontend' separately)"
	@echo "  dev-frontend     Vite dev server on :5173"
	@echo "  test             Backend unit/smoke tests + frontend production build"
	@echo "  test-integration Postgres-backed repository tests (needs TEST_DATABASE_URL)"
	@echo "  lint             Ruff check + format check (backend)"
	@echo "  format           Auto-format backend with Ruff"
	@echo "  typecheck        Mypy on backend app/"
	@echo "  migrate          Alembic upgrade head"
	@echo "  docker-up        docker compose up --build"
	@echo "  docker-down      docker compose down"
	@echo "  eval             CLI Daily Brief demo (needs OPENROUTER_API_KEY)"

install:
	cd $(BACKEND) && uv sync --extra dev
	cd $(FRONTEND) && npm ci

dev:
	docker compose up -d postgres
	cd $(BACKEND) && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-frontend:
	cd $(FRONTEND) && npm run dev

test: test-backend
	cd $(FRONTEND) && npm ci && npm run build

test-backend:
	cd $(BACKEND) && uv run pytest -q

test-integration:
	cd $(BACKEND) && TEST_DATABASE_URL="$(TEST_DATABASE_URL)" uv run pytest -q tests/test_eval.py tests/test_memory.py

lint:
	cd $(BACKEND) && uv run ruff check . && uv run ruff format --check .

format:
	cd $(BACKEND) && uv run ruff format .

typecheck:
	cd $(BACKEND) && uv run mypy app

migrate:
	cd $(BACKEND) && uv run alembic upgrade head

docker-up:
	docker compose up --build

docker-down:
	docker compose down

eval:
	cd $(BACKEND) && uv run python -m scripts.demo brief
