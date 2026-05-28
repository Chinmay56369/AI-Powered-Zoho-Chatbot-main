SHELL := /bin/sh

PYTHON := ./.venv/bin/python
PYTEST := ./.venv/bin/pytest
RUFF := ./.venv/bin/ruff
MYPY := ./.venv/bin/mypy

.PHONY: dev test lint check-venv check-frontend-deps check-mypy

check-venv:
	@test -x "$(PYTHON)" || (echo "Missing .venv. Create it with 'python3 -m venv .venv' and install deps with './.venv/bin/pip install -e .[dev]'." && exit 1)

check-frontend-deps:
	@test -d frontend/node_modules || (echo "Missing frontend dependencies. Run 'cd frontend && npm install'." && exit 1)

check-mypy: check-venv
	@test -x "$(MYPY)" || (echo "Missing mypy in .venv. Install dev dependencies with './.venv/bin/pip install -e .[dev]'." && exit 1)

dev: check-venv check-frontend-deps
	@backend_pid=; frontend_pid=; \
	trap 'test -n "$$backend_pid" && kill $$backend_pid 2>/dev/null; test -n "$$frontend_pid" && kill $$frontend_pid 2>/dev/null' INT TERM EXIT; \
	$(PYTHON) -m uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000 & backend_pid=$$!; \
	npm --prefix frontend run dev -- --host 0.0.0.0 --port 5173 & frontend_pid=$$!; \
	wait $$backend_pid $$frontend_pid

test: check-venv
	$(PYTEST) -q

lint: check-venv check-mypy
	$(RUFF) check backend backend/tests
	$(MYPY) backend