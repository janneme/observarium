SHELL := /bin/bash

VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
REQ := requirements.txt
PYPROJECT := pyproject.toml

.PHONY: init uv-init activate install

.PHONY: test

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

# Initialize venv, ensure runtime/test deps and run the test suite.
test: ## Run pytest using existing venv (requires prior `make init`)
	@if [ -d $(VENV) ]; then \
		$(VENV)/bin/uv run pytest; \
	else \
		echo "Virtualenv not found. Run 'make init' first to create $(VENV)."; exit 1; \
	fi
