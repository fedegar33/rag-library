.DEFAULT_GOAL := help
.PHONY: help setup api web check check-api check-web build

help:
	@echo "make setup      Install locked Python and web dependencies"
	@echo "make api        Run the API at http://127.0.0.1:8000"
	@echo "make web        Run the web app at http://localhost:3000"
	@echo "make check      Run backend and frontend checks"
	@echo "make check-api  Run offline Python tests and Ruff checks"
	@echo "make check-web  Run ESLint and TypeScript checks"
	@echo "make build      Build the web app for production"

setup:
	uv sync --locked
	pnpm --dir web install --frozen-lockfile

api:
	uv run uvicorn rag_library.main:app --reload

web:
	pnpm --dir web dev

check: check-api check-web

check-api:
	LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false uv run python -m unittest discover -s tests
	uv run ruff check .
	uv run ruff format --check .

check-web:
	pnpm --dir web lint
	pnpm --dir web typecheck

build:
	pnpm --dir web build
