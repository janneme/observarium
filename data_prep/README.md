Usage
-----

This folder contains scripts and pipelines to prepare catalogue data.

Make targets
- `make init` — create a Python venv, install dependencies (prefers `pyproject.toml` via `uv`), and open an activated shell.
- `make activate` — open an activated shell using the existing `.venv` (run `make init` first if missing).
- `make install` — create a venv and install from `requirements.txt` (fallback).

CLI (entry point: `main.py`)
- `--only <category>`: run only the named category. Example: `--only stars` runs a basic star-only pipeline (no variable-star enrichment).
- `--group <name>`: run a predefined group of related pipelines. Currently supported:
  - `--group stars`: runs `variable_stars`, then `stars`, then `double_stars` (fetches everything related to stars).

Examples
```bash
# Basic star run (only core star data)
python main.py --only stars

# Full star group (variables + stars + double-stars)
python main.py --group stars

# Initialize environment and open an activated shell
make -C data_prep init

# Activate an existing venv shell later
make -C data_prep activate
```

Notes
- `--only stars` is intentionally minimal to allow fast, incremental runs.
- `--group stars` is for a full refresh of all star-related data; more groups may be added later.
