PYTHON ?= python3
VENV   ?= .venv
BIN    := $(VENV)/bin
PYTHON_BIN := $(BIN)/python
UV     ?= uv
GATEWAY := $(BIN)/mcp-gateway
CONFIG  ?= examples/mcp-gateway.yaml
PORT    ?= 8765
HOST    ?= 127.0.0.1

.DEFAULT_GOAL := help

.PHONY: help install run stop test test-cov lint format typecheck \
        validate-specs clean clean-all example-mock

help: ## Show available targets
	@awk 'BEGIN {FS = ":.*##"; printf "Usage:\n  make \033[36m<target>\033[0m\n\nTargets:\n"} \
	  /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

install: ## Create venv and install dev dependencies
	@if [ ! -d "$(VENV)" ]; then $(UV) venv; fi
	$(UV) pip install -e ".[dev]"

run: ## Start the gateway with CONFIG (default: examples/mcp-gateway.yaml)
	@if [ ! -x "$(PYTHON_BIN)" ]; then $(MAKE) install; fi
	@if [ ! -x "$(GATEWAY)" ]; then echo "mcp-gateway not installed; run 'make install' first"; exit 1; fi
	@if [ -z "$$PYTHON" ]; then \
	  echo "Tip: export PYTHON=\"$(PWD)/$(PYTHON_BIN)\" so stdio backends can import the venv"; \
	fi
	$(GATEWAY) --config $(CONFIG) --host $(HOST) --port $(PORT)

run-debug: ## Start the gateway with debug logging
	$(GATEWAY) --config $(CONFIG) --host $(HOST) --port $(PORT) --log-level debug

stop: ## Stop the gateway running on $(HOST):$(PORT)
	@lsof -ti tcp:$(PORT) 2>/dev/null | xargs -r kill -TERM || true

test: ## Run the test suite
	$(BIN)/pytest -q

test-cov: ## Run tests with coverage report
	$(BIN)/pytest --cov=$(BIN)/../src/mcp_gateway --cov-report=term-missing

test-watch: ## Run tests in watch mode (requires pytest-watch)
	$(BIN)/pytest-watch

lint: ## Run ruff linter
	$(BIN)/ruff check src tests

format: ## Auto-format with ruff
	$(BIN)/ruff format src tests
	$(BIN)/ruff check --fix src tests

typecheck: ## Run ty type checker
	$(BIN)/ty check src

validate-specs: ## Validate OpenSpec specs and changes
	openspec validate --strict || true
	@for c in $$(openspec list --json | python3 -c "import json,sys; [print(x['name']) for x in json.load(sys.stdin)['changes']]"); do \
	  echo "validating $$c"; openspec validate $$c; \
	done

example-mock: ## Run the example mock backend in isolation (for debugging stdio)
	$(PYTHON_BIN) examples/mock_backend.py

clean: ## Remove caches and build artifacts
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage*

clean-all: clean ## Also remove the virtual environment
	rm -rf $(VENV)