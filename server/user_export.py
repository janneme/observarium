"""Export one user's data from cloud/local storage to ./users/{username}/ for
git-backed backup - observations, finding paths, telescopes, eyepieces, lists.
Excludes performance data (it isn't a per-user category to begin with).

Reads directly from the storage backend (STORAGE=local|s3, default s3 via the
Makefile target) - not through the Lambda HTTP API, same as data_upload.py/
perf_report.py.

Usage:
    STORAGE=local PYTHONPATH=.. uv run python user_export.py --user alice
    STORAGE=s3 DATA_BUCKET=... PYTHONPATH=.. uv run python user_export.py --user alice
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from python_lib.storage import backend as storage_backend

from user_categories import CATEGORY_KEY_FNS, REPO_ROOT


def export_user(username: str, out_dir: Path | None = None) -> dict[str, str]:
    """Export username's data to out_dir/{category}.json (default
    ./users/{username}/), pretty-printed (indent=2) for readable git diffs.
    Returns {category: "exported" | "not found"}."""
    backend = storage_backend.get_backend()
    target_dir = out_dir or (REPO_ROOT / "users" / username)
    results = {}
    for category, key_fn in CATEGORY_KEY_FNS.items():
        key = key_fn(username)
        if not backend.exists(key):
            results[category] = "not found"
            continue
        target_dir.mkdir(parents=True, exist_ok=True)
        data = json.loads(backend.read_bytes(key))
        (target_dir / f"{category}.json").write_text(json.dumps(data, indent=2) + "\n")
        results[category] = "exported"
    return results


def main() -> None:
    """Parse --user and export that user's data to ./users/{username}/."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", required=True, help="Username to export")
    args = parser.parse_args()

    target_dir = REPO_ROOT / "users" / args.user
    print(f"Exporting '{args.user}' to {target_dir}")
    for category, status in export_user(args.user).items():
        print(f"  {category}: {status}")


if __name__ == "__main__":
    main()
