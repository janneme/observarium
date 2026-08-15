"""One-off, idempotent migration from the old flat storage layout to the new
users/app-data layout.

Old:  {category}/{sub}.json          (sub = opaque Cognito UUID)
      manifest.json, manifest.hash, images.zip, performance/events.json
      stars_t1_mag*.zip, objects_mag*.zip, t2_*_mag*.zip (top-level chunk files)
New:  users/{username}/{category}.json  (username = human-readable Cognito login)
      app-data/manifest.json, app-data/manifest.hash, app-data/images.zip,
      app-data/{chunk filename}
      users/_anonymized/performance.json  (usage telemetry - user-collected,
      not app-runtime data, so it lives under users/ despite having no real
      Cognito owner; "_anonymized" is reserved and never a real username)

Safe to re-run: each item is only copied+deleted if the new key doesn't
already exist and the old one does; anything already migrated (or never
present) is left alone.

Requires AWS credentials with cognito-idp:ListUsers on COGNITO_USER_POOL_ID
(the same profile already used for deploy-lambda/data-upload-s3), plus
COGNITO_REGION/COGNITO_USER_POOL_ID set in the environment (same as the
running server).

Usage:
    STORAGE=local PYTHONPATH=.. uv run python migrate_storage.py
    STORAGE=s3 DATA_BUCKET=... PYTHONPATH=.. uv run python migrate_storage.py
"""
from __future__ import annotations

import boto3
from python_lib.storage import backend as storage_backend

from handler import COGNITO_REGION, COGNITO_USER_POOL_ID, USAGE_STATS_KEY
from user_categories import CATEGORY_KEY_FNS

# Each entry lists every place the item may currently live (older partial
# migration runs can leave it at an intermediate key) - the first one found
# is moved to new_key.
APP_DATA_MOVES = [
    (["manifest.json"], "app-data/manifest.json"),
    (["manifest.hash"], "app-data/manifest.hash"),
    (["images.zip"], "app-data/images.zip"),
    (["performance/events.json", "app-data/performance/events.json"], USAGE_STATS_KEY),
]

# Star-catalogue chunk files are top-level and dynamically named (one per
# magnitude/zone), so they're matched by prefix rather than listed by hand.
CHUNK_FILE_PREFIXES = ("stars_t1_", "objects_", "t2_")


def list_cognito_users() -> list[tuple[str, str]]:
    """Return [(username, sub), ...] for every user in COGNITO_USER_POOL_ID."""
    if not COGNITO_USER_POOL_ID:
        raise RuntimeError("COGNITO_USER_POOL_ID not set in environment")
    client = boto3.client("cognito-idp", region_name=COGNITO_REGION)
    users = []
    paginator = client.get_paginator("list_users")
    for page in paginator.paginate(UserPoolId=COGNITO_USER_POOL_ID):
        for u in page.get("Users", []):
            username = u.get("Username")
            attrs = u.get("Attributes", [])
            sub = next((a.get("Value") for a in attrs if a.get("Name") == "sub"), None)
            if username and sub:
                users.append((username, sub))
    return users


def migrate_key(backend, old_key: str, new_key: str) -> str:
    """Copy old_key -> new_key then delete old_key. Returns a status string."""
    return migrate_key_multi(backend, [old_key], new_key)


def migrate_key_multi(backend, old_keys: list[str], new_key: str) -> str:
    """Like migrate_key, but tries each of old_keys in order and moves the
    first one found. Returns a status string."""
    if backend.exists(new_key):
        return "already migrated"
    for old_key in old_keys:
        if backend.exists(old_key):
            backend.write_bytes(new_key, backend.read_bytes(old_key))
            backend.delete_bytes(old_key)
            return f"migrated (from {old_key})"
    return "not found"


def migrate_chunk_files(backend) -> list[tuple[str, str]]:
    """Move every top-level star-catalogue chunk file under app-data/.
    Returns [(old_key, status), ...]."""
    results = []
    for key in backend.list_keys(""):
        if "/" in key or not key.startswith(CHUNK_FILE_PREFIXES):
            continue
        status = migrate_key(backend, key, f"app-data/{key}")
        results.append((key, status))
    return results


def main() -> None:
    """Migrate every Cognito user's data plus the shared app-data files from
    the old flat storage layout to the new users/app-data layout."""
    backend = storage_backend.get_backend()

    print("=== Per-user data ===")
    users = list_cognito_users()
    print(f"Found {len(users)} Cognito user(s)")
    for username, sub in users:
        for category, new_key_fn in CATEGORY_KEY_FNS.items():
            old_key = f"{category}/{sub}.json"
            status = migrate_key(backend, old_key, new_key_fn(username))
            print(f"  {username} / {category}: {status}")

    print("\n=== Star-catalogue chunk files ===")
    for old_key, status in migrate_chunk_files(backend):
        print(f"  {old_key}: {status}")

    print("\n=== Shared app data ===")
    for old_keys, new_key in APP_DATA_MOVES:
        status = migrate_key_multi(backend, old_keys, new_key)
        print(f"  {' or '.join(old_keys)} -> {new_key}: {status}")


if __name__ == "__main__":
    main()
