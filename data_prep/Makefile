SHELL := /bin/bash

VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
REQ := requirements.txt
PYPROJECT := pyproject.toml

.PHONY: init uv-init activate install
.PHONY: test
.PHONY: lint lint-fix

.PHONY: test

.PHONY: lint

# Default init: prefer pyproject.toml + uv, fall back to requirements.txt
init:
	@if [ -f $(PYPROJECT) ]; then $(MAKE) uv-init; else $(MAKE) install; fi

# Create venv and install using `uv` from pyproject.toml
uv-init:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip setuptools wheel
	# install uv into the venv
	$(PIP) install uv
	# Prefer using uv to install the project and its deps. If uv or the
	# project build fails, fall back to installing runtime deps via pip.
		@# Require uv to perform installs; do not fall back to pip.
		@if command -v $(VENV)/bin/uv >/dev/null 2>&1; then \
			$(VENV)/bin/uv pip install . || { echo "uv pip install failed; aborting."; exit 1; }; \
		else \
			echo "uv not found in venv after install; aborting."; exit 1; \
		fi
	@echo "Virtualenv created at $(VENV). Activate with: . $(VENV)/bin/activate"

activate:
	@if [ -d $(VENV) ]; then . $(VENV)/bin/activate; exec $$SHELL; else echo "Run 'make init' first."; fi

install:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip setuptools wheel
	@if [ -f $(REQ) ]; then $(PIP) install -r $(REQ); else echo "No requirements.txt found in data_prep"; fi

# Run tests: assume the venv is already prepared and only run pytest.
test: ## Run pytest using existing venv (requires prior `make init`)
	$(VENV)/bin/python -m pytest

# Run linters using tools installed in the venv. Do not perform any installs.
lint: ## Run ruff and pylint using existing venv (requires prior `make init`)
	# Exclude build artifacts, the venv directory and tests from analysis
	@printf "\n\033[1;36m❯ ruff check\033[0m\n"; \
	$(VENV)/bin/ruff check . --exclude .venv,build,output,cache,tests; rc=$$?; \
	if [ $$rc -ne 0 ]; then \
		echo "ruff reported issues (exit $$rc); skipping pylint."; \
		exit 0; \
	fi; \
	printf "\n\033[1;36m❯ pylint check\033[0m\n"; \
	$(VENV)/bin/pylint --rcfile=$(CURDIR)/../.pylintrc $(shell find . -name '*.py' -not -path './.venv/*' -not -path './build/*' -not -path './output/*' -not -path './cache/*' -not -path './tests/*' -not -path '../tests/*') || true

# Auto-fix lintable issues with ruff, then re-run lint target
lint-fix: ## Run ruff --fix on source (requires prior `make init`)
	@echo "Running ruff --fix (source only, tests excluded)..."
	@$(VENV)/bin/ruff check . --fix --exclude .venv,build,output,cache,tests || true
	@$(MAKE) -C $(CURDIR) lint
