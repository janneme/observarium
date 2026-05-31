SHELL := /bin/bash

VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
REQ := requirements.txt
PYPROJECT := pyproject.toml

.PHONY: init uv-init activate install

# Default init: prefer pyproject.toml + uv, fall back to requirements.txt
init:
	@if [ -f $(PYPROJECT) ]; then $(MAKE) uv-init; else $(MAKE) install; fi

# Create venv and install using `uv` from pyproject.toml
uv-init:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip setuptools wheel
	# install uv into the venv
	$(PIP) install uv
	# use uv to install the project (reads pyproject.toml) via uv's pip wrapper
	@if command -v $(VENV)/bin/uv >/dev/null 2>&1; then $(VENV)/bin/uv pip install . || $(VENV)/bin/python -m pip install .; else $(PIP) install -r $(REQ); fi
	. $(VENV)/bin/activate; exec $$SHELL

activate:
	@if [ -d $(VENV) ]; then . $(VENV)/bin/activate; exec $$SHELL; else echo "Run 'make init' first."; fi

install:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip setuptools wheel
	@if [ -f $(REQ) ]; then $(PIP) install -r $(REQ); else echo "No requirements.txt found in data_prep"; fi
