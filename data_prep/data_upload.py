"""Bundle objects and images and sync to storage backend.

Usage:
  python3 data_prep/data_upload.py            # upload all locally prepared magnitude sets
  python3 data_prep/data_upload.py --mag 12   # upload only magnitude 12
"""
from __future__ import annotations

import argparse
import hashlib
import json
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


def _filter_dso_by_mag(dso_grouped: dict, mag_limit: float) -> dict:
    """Remove non-Messier DSOs whose magnitude exceeds `mag_limit`."""
    filtered: dict = {}
    for constellation, objects in dso_grouped.items():
        kept = [
            obj for obj in objects
            if "m" in obj  # Messier objects always included
            or obj.get("mag") is None  # no magnitude data → include
            or obj["mag"] <= mag_limit
        ]
        if kept:
            filtered[constellation] = kept
    return filtered


def _collect_json(mag: int | None = None) -> dict:
    out: dict = {}
    for p in sorted(DATA_OUT.glob("*.json")):
        name = p.name
        # Stars are now delivered via CSV; exclude all stars JSON files.
        if name.startswith("stars.m") or name.startswith("stars_t1.") or name.startswith(
            "stars_t2."
        ):
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
                data = json.load(fh)
            except Exception:
                data = fh.read().decode("utf-8")
        if name == "dso.json" and mag is not None and isinstance(data, dict):
            data = _filter_dso_by_mag(data, 0.8 * mag)
        out[p.stem] = data
    return out


def _find_csv(mag: int | None, prefix: str) -> Path | None:
    """Return the CSV path matching prefix + mag tag, or most recent."""
    if mag is not None:
        p = DATA_OUT / f"{prefix}.m{mag}.csv"
        if p.exists():
            return p
    matches = sorted(DATA_OUT.glob(f"{prefix}.m*.csv"))
    return matches[-1] if matches else None


def _count_t1_stats(t1_path: Path) -> dict:
    """Count T1 stars, variable stars, and double stars in the T1 CSV.

    T1 CSV header: ra,de,mg,cl,hp,hd,sp,ds,pr,pd,fl,by,db,nm,nt,sm
    Index 2 = mg (colon-separated range means variable).
    Index 12 = db (non-empty means double star).
    """
    stars = 0
    variable = 0
    double = 0
    with t1_path.open("r", encoding="utf-8") as fh:
        first = True
        for line in fh:
            if first:
                first = False
                continue
            line = line.rstrip("\n")
            if not line.strip():
                continue
            stars += 1
            cols = line.split(",", 13)
            if len(cols) > 2 and ":" in cols[2]:
                variable += 1
            if len(cols) > 12 and cols[12]:
                double += 1
    return {"stars": stars, "variable": variable, "double": double}


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


def _pack_t2_chunks(
    t2_path: Path, out_dir: Path, mag: int
) -> tuple[list[tuple[str, list[int]]], dict]:
    """Bin-pack zones from T2 CSV into chunk ZIPs. Returns (chunks, stats).

    T2 CSV format: z,ra,de,mg,cl,hp,hd,sp,ds,pr,pd (no header in zone blobs).
    Index 3 = mg; colon-separated range means variable star.
    """
    zones: dict[int, list[str]] = {}
    t2_stars = 0
    t2_variable = 0
    with t2_path.open("r", encoding="utf-8") as fh:
        first = True
        for line in fh:
            line = line.rstrip("\n")
            if first:
                first = False
                continue  # skip header
            if not line.strip():
                continue
            cols = line.split(",", 4)
            zone = int(cols[0])
            zones.setdefault(zone, []).append(line)
            t2_stars += 1
            if len(cols) > 3 and ":" in cols[3]:
                t2_variable += 1

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
            chunk_name = f"t2_{chunk_idx:03d}_mag{mag}.zip"
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
        chunk_name = f"t2_{chunk_idx:03d}_mag{mag}.zip"
        _write_chunk_zip(out_dir / chunk_name, current_zone_data)
        chunks.append((chunk_name, list(current_zones)))

    return chunks, {"stars": t2_stars, "variable": t2_variable}


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


def _detect_mags() -> list[int]:
    """Return sorted list of magnitude values with locally prepared output files."""
    mags: set[int] = set()
    for p in DATA_OUT.glob("stars_t1.m*.csv"):
        try:
            m = int(p.stem.split(".m")[1])
            mags.add(m)
        except (IndexError, ValueError):
            pass
    return sorted(mags)


def _upload_one_mag(mag: int, storage: backend.Backend) -> dict:
    """Build, upload, and return the manifest set entry for one magnitude."""
    objects = _collect_json(mag=mag)
    t1_path = _find_csv(mag, "stars_t1")
    t2_path = _find_csv(mag, "stars_t2")

    objects_zip = TMP_DIR / f"objects_mag{mag}.zip"
    stars_t1_zip = TMP_DIR / f"stars_t1_mag{mag}.zip"

    print(f"\n--- Magnitude {mag} ---")

    print(f"  Building {objects_zip.name}...")
    _write_objects_zip(objects, objects_zip)

    t1_stats: dict = {"stars": 0, "variable": 0, "double": 0}
    if t1_path:
        t1_stats = _count_t1_stats(t1_path)
        _write_stars_t1_zip(t1_path, stars_t1_zip)
    else:
        print(f"  WARNING: stars_t1 CSV not found for mag {mag}, skipped")

    t2_chunks: list[tuple[str, list[int]]] = []
    t2_stats: dict = {"stars": 0, "variable": 0}
    if t2_path:
        t2_chunks, t2_stats = _pack_t2_chunks(t2_path, TMP_DIR, mag)
        print(f"  {len(t2_chunks)} T2 chunks produced")
    else:
        print(f"  WARNING: stars_t2 CSV not found for mag {mag}, no T2 chunks")

    total_size = 0
    if stars_t1_zip.exists():
        total_size += stars_t1_zip.stat().st_size
        _sync_file(stars_t1_zip, stars_t1_zip.name, "T1 stars", t1_stats["stars"], storage)
    total_size += objects_zip.stat().st_size
    _sync_file(objects_zip, objects_zip.name, "sources", len(objects), storage)
    for name, zones in t2_chunks:
        chunk_path = TMP_DIR / name
        total_size += chunk_path.stat().st_size
        _sync_file(chunk_path, name, "T2 zones", len(zones), storage)

    set_entry: dict = {
        "mag": mag,
        "total_size": total_size,
        "stats": {
            "stars_t1": t1_stats["stars"],
            "variable_t1": t1_stats["variable"],
            "double_t1": t1_stats["double"],
            "stars_t2": t2_stats["stars"],
            "variable_t2": t2_stats["variable"],
        },
        "stars_t1": {
            "filename": stars_t1_zip.name,
            "hash": "sha256:" + _sha256(stars_t1_zip) if stars_t1_zip.exists() else "",
            "size": stars_t1_zip.stat().st_size if stars_t1_zip.exists() else 0,
        },
        "objects": {
            "filename": objects_zip.name,
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
    return set_entry


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload data bundles to storage backend.")
    parser.add_argument("--mag", type=int, default=None, help="Upload only this magnitude set.")
    args = parser.parse_args()

    TMP_DIR.mkdir(exist_ok=True)

    if args.mag is not None:
        mags = [args.mag]
    else:
        mags = _detect_mags()
        if not mags:
            print("ERROR: No locally prepared magnitude sets found in output/", file=sys.stderr)
            return 1
        print(f"Detected magnitude sets: {mags}")

    storage = backend.get_backend()

    # Upload images once, independent of magnitude
    images_zip = TMP_DIR / "images.zip"
    num_images = sum(1 for p in IMAGES_DIR.rglob("*") if p.is_file()) if IMAGES_DIR.exists() else 0
    print("\nBuilding images.zip...")
    _write_images_zip(images_zip)
    _sync_file(images_zip, "images.zip", "images", num_images, storage)

    sets = []
    for mag in mags:
        set_entry = _upload_one_mag(mag, storage)
        sets.append(set_entry)

    print("\nGenerating manifest...")
    manifest = {"sets": sets}
    manifest_bytes = json.dumps(manifest, separators=(",", ":")).encode("utf-8")
    manifest_path = TMP_DIR / "manifest.json"
    manifest_hash_path = TMP_DIR / "manifest.hash"
    manifest_path.write_bytes(manifest_bytes)
    manifest_hash_path.write_text(hashlib.sha256(manifest_bytes).hexdigest())

    _sync_file(manifest_path, "manifest.json", "entries", len(sets), storage)
    _sync_file(manifest_hash_path, "manifest.hash", "hash", 0, storage)

    print(f"\nDone. Uploaded {len(sets)} magnitude set(s): {[s['mag'] for s in sets]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
