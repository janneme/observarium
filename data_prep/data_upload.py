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
from datetime import date
from pathlib import Path

# Ensure repo root on sys.path so python_lib is importable
ROOT = Path(__file__).resolve().parent
repo_root = ROOT.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from python_lib.storage import backend  # noqa: E402  # pylint: disable=wrong-import-position

DATA_OUT = ROOT / "output"
IMAGES_DIR = DATA_OUT / "images"
TMP_DIR = ROOT / "tmp"

TARGET_CHUNK_BYTES = 5 * 1024 * 1024
COMPRESS_RATIO = 3.0


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
        # Stars are now delivered via CSV; exclude all stars JSON files.
        if name.startswith("stars.m") or name.startswith("stars_t1.") or name.startswith("stars_t2."):
            continue
        if mag is not None:
            # For double_stars: prefer mag-specific file; skip generic when mag file exists
            if name == "double_stars.json" and (DATA_OUT / f"double_stars.m{mag}.json").exists():
                continue
            if name.startswith("double_stars.m") and name != f"double_stars.m{mag}.json":
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


def _find_csv(mag: int | None, prefix: str) -> Path | None:
    """Return the CSV path matching prefix + mag tag, or most recent."""
    if mag is not None:
        p = DATA_OUT / f"{prefix}.m{mag}.csv"
        if p.exists():
            return p
    matches = sorted(DATA_OUT.glob(f"{prefix}.m*.csv"))
    return matches[-1] if matches else None


def _write_stars_t1_zip(t1_path: Path, target: Path) -> None:
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(t1_path, arcname="stars_t1.csv")


def _write_objects_zip(objects_obj: dict, target: Path) -> None:
    tmp_json = target.with_suffix(".json.tmp")
    with tmp_json.open("wb") as fh:
        fh.write(json.dumps(objects_obj, separators=(",", ":")).encode("utf-8"))
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(tmp_json, arcname="objects.json")
    tmp_json.unlink()


def _write_chunk_zip(target: Path, zone_data: dict[int, str]) -> None:
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for zone, csv in sorted(zone_data.items()):
            zf.writestr(f"{zone:04d}.csv", csv)


def _pack_t2_chunks(t2_path: Path, out_dir: Path) -> list[tuple[str, list[int]]]:
    """Bin-pack zones from T2 CSV into chunk ZIPs. Returns list of (filename, zones)."""
    zones: dict[int, list[str]] = {}
    with t2_path.open("r", encoding="utf-8") as fh:
        first = True
        for line in fh:
            line = line.rstrip("\n")
            if first:
                first = False
                continue  # skip header
            if not line.strip():
                continue
            comma = line.index(",")
            zone = int(line[:comma])
            zones.setdefault(zone, []).append(line)

    chunks: list[tuple[str, list[int]]] = []
    chunk_idx = 0
    current_zones: list[int] = []
    current_estimated = 0.0
    current_zone_data: dict[int, str] = {}

    for zone_num in sorted(zones.keys()):
        zone_lines = zones[zone_num]
        zone_csv = "\n".join(zone_lines)
        zone_estimated = len(zone_csv.encode("utf-8")) / COMPRESS_RATIO
        if current_zones and current_estimated + zone_estimated > TARGET_CHUNK_BYTES:
            chunk_name = f"t2_{chunk_idx:03d}.zip"
            _write_chunk_zip(out_dir / chunk_name, current_zone_data)
            chunks.append((chunk_name, list(current_zones)))
            chunk_idx += 1
            current_zones = []
            current_estimated = 0.0
            current_zone_data = {}
        current_zones.append(zone_num)
        current_estimated += zone_estimated
        current_zone_data[zone_num] = zone_csv

    if current_zones:
        chunk_name = f"t2_{chunk_idx:03d}.zip"
        _write_chunk_zip(out_dir / chunk_name, current_zone_data)
        chunks.append((chunk_name, list(current_zones)))

    return chunks


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
    TMP_DIR.mkdir(exist_ok=True)

    objects = _collect_json(mag=mag)
    t1_path = _find_csv(mag, "stars_t1")
    t2_path = _find_csv(mag, "stars_t2")

    objects_zip = TMP_DIR / "objects.zip"
    stars_t1_zip = TMP_DIR / "stars_t1.zip"
    images_zip = TMP_DIR / "images.zip"

    print("Building objects.zip...")
    _write_objects_zip(objects, objects_zip)

    print("Building stars_t1.zip...")
    if t1_path:
        _write_stars_t1_zip(t1_path, stars_t1_zip)
    else:
        print("  WARNING: stars_t1 CSV not found, skipped")

    print("Packing T2 chunks...")
    t2_chunks: list[tuple[str, list[int]]] = []
    if t2_path:
        t2_chunks = _pack_t2_chunks(t2_path, TMP_DIR)
        print(f"  {len(t2_chunks)} chunks produced")
    else:
        print("  WARNING: stars_t2 CSV not found, no T2 chunks")

    print("Building images.zip...")
    _write_images_zip(images_zip)

    print("Generating manifest...")
    manifest = {
        "version": date.today().isoformat(),
        "stars_t1": {
            "filename": "stars_t1.zip",
            "hash": "sha256:" + _sha256(stars_t1_zip) if stars_t1_zip.exists() else "",
            "size": stars_t1_zip.stat().st_size if stars_t1_zip.exists() else 0,
        },
        "objects": {
            "filename": "objects.zip",
            "hash": "sha256:" + _sha256(objects_zip),
            "size": objects_zip.stat().st_size,
        },
        "t2_chunks": [
            {
                "filename": name,
                "hash": "sha256:" + _sha256(TMP_DIR / name),
                "size": (TMP_DIR / name).stat().st_size,
                "zones": zones,
            }
            for name, zones in t2_chunks
        ],
    }
    manifest_bytes = json.dumps(manifest, separators=(",", ":")).encode("utf-8")
    manifest_path = TMP_DIR / "manifest.json"
    manifest_hash_path = TMP_DIR / "manifest.hash"
    manifest_path.write_bytes(manifest_bytes)
    manifest_hash_path.write_text(hashlib.sha256(manifest_bytes).hexdigest())

    storage = backend.get_backend()
    num_sources = len(objects)
    num_images = sum(1 for p in IMAGES_DIR.rglob("*") if p.is_file()) if IMAGES_DIR.exists() else 0

    _sync_file(objects_zip, "objects.zip", "sources", num_sources, storage)
    if stars_t1_zip.exists():
        _sync_file(stars_t1_zip, "stars_t1.zip", "T1 stars", 0, storage)
    for name, zones in t2_chunks:
        _sync_file(TMP_DIR / name, name, "T2 zones", len(zones), storage)
    _sync_file(manifest_path, "manifest.json", "entries", 0, storage)
    _sync_file(manifest_hash_path, "manifest.hash", "hash", 0, storage)
    _sync_file(images_zip, "images.zip", "images", num_images, storage)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
