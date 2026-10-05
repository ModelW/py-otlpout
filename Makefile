# Root Makefile: format (ruff), lint (ruff) and type-check (mypy) the whole
# workspace, plus the library and pet-project test suites.

.PHONY: help format lint typecheck test test-django test-fastapi test-all clean

PYTHON_BIN ?= uv run python

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

clean: format lint ## Format then lint (leaves the tree ready to commit)

format: ## Format all Python code (ruff: import sorting + formatting)
	$(PYTHON_BIN) -m ruff check --fix --select I .
	$(PYTHON_BIN) -m ruff format .

lint: typecheck ## Lint (ruff) and type-check all Python code
	$(PYTHON_BIN) -m ruff check .
	$(PYTHON_BIN) -m ruff format --check .

typecheck: ## Type-check with mypy
	$(PYTHON_BIN) -m mypy .

test: ## Run the library test suite
	uv run pytest

test-django: ## Run the pet Django project's tests
	cd examples/django_pet && uv run pytest

test-fastapi: ## Run the pet FastAPI project's tests
	cd examples/fastapi_pet && uv run pytest

test-all: test test-django test-fastapi ## Run every test suite
