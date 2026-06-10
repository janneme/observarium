.DEFAULT_GOAL := help

unexport VIRTUAL_ENV

.PHONY: help dev sync lint test

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  %-16s %s\n", $$1, $$2}'

dev: ## Run the local development server on port 8787
	@if [ -f .env ]; then export $$(grep -v '^#' .env | xargs); fi; PYTHONPATH=.. VIRTUAL_ENV= uv run python local_server.py --port 8787

sync: ## Install/update dependencies with uv
	uv sync

lint: ## Run ruff and pylint
	PYTHONPATH=.. uv run ruff check .
	PYTHONPATH=.. uv run pylint handler.py local_server.py

test: ## Run tests (placeholder)
	uv run pytest -q
