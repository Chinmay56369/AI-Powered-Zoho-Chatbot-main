.PHONY: dev backend frontend test lint format typecheck

dev:
	@echo "Starting backend + frontend"
	make -j2 backend frontend

backend:
	uvicorn backend.app.main:app --reload

frontend:
	cd frontend && npm run dev

test:
	pytest

lint:
	ruff check .
	mypy backend

format:
	ruff check . --fix

typecheck:
	mypy backend