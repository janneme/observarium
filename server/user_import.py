"""Import one user's data from ./users/{username}/ (as written by
user_export.py) back into cloud/local storage, OVERWRITING whatever is
currently there for that user. Requires typing the username again to
confirm, unless --yes is passed.

Usage:
    STORAGE=local PYTHONPATH=.. uv run python user_import.py --user alice
    STORAGE=s3 DATA_BUCKET=... PYTHONPATH=.. \\
        uv run python user_import.py --user alice --yes
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from python_lib.storage import backend as storage_backend

from user_categories import CATEGORY_KEY_FNS, REPO_ROOT


def find_local_files(username: str, in_dir: Path | None = None) -> dict[str, Path]:
    """Return {category: local_path} for every category file present under
    in_dir (default ./users/{username}/)."""
    source_dir = in_dir or (REPO_ROOT / "users" / username)
    found = {}
    for category in CATEGORY_KEY_FNS:
        p = source_dir / f"{category}.json"
        if p.exists():
            found[category] = p
    return found


def import_user(username: str, local_files: dict[str, Path]) -> dict[str, str]:
    """Write each local_files[category] to its remote key, overwriting
    whatever is currently there. Returns {category: "imported"}."""
    backend = storage_backend.get_backend()
    results = {}
    for category, path in local_files.items():
        key = CATEGORY_KEY_FNS[category](username)
        backend.write_bytes(key, path.read_bytes())
        results[category] = "imported"
    return results


def main() -> None:
    """Parse --user/--yes and import that user's data from
    ./users/{username}/, overwriting the remote copy."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", required=True, help="Username to import")
    parser.add_argument(
        "--yes", action="store_true", help="Skip the confirmation prompt"
    )
    args = parser.parse_args()

    backend = storage_backend.get_backend()
    local_files = find_local_files(args.user)
    if not local_files:
        local_dir = REPO_ROOT / "users" / args.user
        print(f"No local files found under {local_dir} - nothing to import.")
        return

    print(f"About to OVERWRITE the following for '{args.user}':")
    for category, path in local_files.items():
        key = CATEGORY_KEY_FNS[category](args.user)
        print(f"  {category}: {path} -> {backend.get_location(key)}")

    if not args.yes:
        confirm = input(f"\nType the username ('{args.user}') to confirm overwrite: ")
        if confirm != args.user:
            print("Aborted - typed username did not match.")
            sys.exit(1)

    for category, status in import_user(args.user, local_files).items():
        print(f"  {category}: {status}")


if __name__ == "__main__":
    main()
