"""Bundle objects and images and sync to storage backend.

Usage:
  MAG=9 STORAGE=local python3 data_prep/data_upload.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import zipfile
from pathlib import Path

# Ensure repo root on sys.path so python_lib is importable
ROOT = Path(__file__).resolve().parent
repo_root = ROOT.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from python_lib.storage import backend  # noqa: E402  # pylint: disable=wrong-import-position

DATA_OUT = ROOT / "output"
IMAGES_DIR = DATA_OUT / "images"


def human_size(n: int) -> str:
    # Human-readable sizes: B, KB, MB, GB, TB
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if unit == "B":
            if size < 1024:
                return f"{int(size)}B"
        else:
            if size < 1024:
                return f"{size:.2f}{unit}"
        size /= 1024.0
    return f"{size:.2f}PB"


def _collect_json(mag: int | None = None) -> dict:
    out: dict = {}
    for p in sorted(DATA_OUT.glob("*.json")):
        name = p.name
        # If mag provided, include only stars.m{mag}.json for stars files
        if mag is not None and name.startswith("stars") and not name.startswith(f"stars.m{mag}"):
            continue
        # skip images manifest if any
        if name == "images.json":
            continue
        with p.open("rb") as fh:
            try:
                out[p.stem] = json.load(fh)
            except Exception:
                out[p.stem] = fh.read().decode("utf-8")
    return out


def _write_objects_zip(objects_obj: dict, target: Path) -> None:
    tmp_json = target.with_suffix(".json.tmp")
    with tmp_json.open("wb") as fh:
        fh.write(json.dumps(objects_obj, separators=(",", ":")).encode("utf-8"))
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(tmp_json, arcname="objects.json")
    tmp_json.unlink()


def _write_images_zip(target: Path) -> None:
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_STORED) as zf:
        if IMAGES_DIR.exists():
            for p in sorted(IMAGES_DIR.glob("**/*")):
                if p.is_file():
                    rel = p.relative_to(IMAGES_DIR)
                    zf.write(p, arcname=str(rel))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _sync_file(
    path: Path,
    key: str,
    count_label: str,
    count: int,
    storage: backend.Backend,
) -> None:
    if not path.exists():
        print(f"{key}: missing; skipped")
        return
    size = path.stat().st_size
    local_hash = _sha256(path)
    remote_hash = storage.get_hash(key)
    target = storage.get_location(key)
    if remote_hash != local_hash:
        storage.write_bytes(key, path.read_bytes())
        action = "uploaded"
    else:
        action = "unchanged"
    print(f"{key}: {count} {count_label}, {human_size(size)} -> {target} ({action})")


def main() -> int:
    mag_env = os.environ.get("MAG") or os.environ.get("mag")
    mag = int(mag_env) if mag_env and mag_env.isdigit() else None

    objects = _collect_json(mag=mag)
    tmp_dir = ROOT / "tmp"
    tmp_dir.mkdir(exist_ok=True)
    objects_zip = tmp_dir / "objects.zip"
    images_zip = tmp_dir / "images.zip"

    print("Building objects.zip...")
    _write_objects_zip(objects, objects_zip)
    print("Building images.zip...")
    _write_images_zip(images_zip)

    num_sources = len(objects)
    num_images = sum(1 for p in IMAGES_DIR.rglob("*") if p.is_file()) if IMAGES_DIR.exists() else 0

    storage = backend.get_backend()
    _sync_file(objects_zip, "objects.zip", "sources", num_sources, storage)
    _sync_file(images_zip, "images.zip", "images", num_images, storage)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
