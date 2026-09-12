.PHONY: install dev-api test lint format typecheck web-install web-dev web-build web-check web-e2e check

install:
	python -m pip install -e '.[dev]'

dev-api:
	@set -a; [ ! -f .env.local ] || . ./.env.local; set +a; \
	uvicorn spotdata.main:app --app-dir apps/api/src --host 0.0.0.0 --port 8000 --reload

test:
	pytest

lint:
	ruff check .

format:
	ruff format .

typecheck:
	mypy

web-install:
	npm ci

web-dev:
	@set -a; [ ! -f .env.local ] || . ./.env.local; set +a; \
	PECHE_TN_API_ORIGIN=$${PECHE_TN_API_ORIGIN:-http://127.0.0.1:8000} npm run dev

web-build:
	npm run build

web-check:
	npm run lint && npm run typecheck && npm run build

web-e2e:
	npm run test:e2e

check: lint typecheck test web-check
