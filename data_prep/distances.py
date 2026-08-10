"""Distance overrides for dso.json objects that need a source other than
OpenNGC's own Pax/Redshift columns (parsed directly in dso.py).

Two sources, both applied as a post-processing pass over already-built DSO
objects (matched by catalogue id or literal name, not by raw CSV row):

- Harris (1996, 2010 edition) globular cluster catalogue: OpenNGC's Pax is
  demonstrably unreliable for globular clusters (crowded-field Gaia parallax
  bias - verified against M13: naive Pax inversion gives ~12.3 kpc vs. the
  accepted ~7.1 kpc), so globular clusters get their distance from here
  instead, keyed by NGC number.
- A small hand-curated CSV (sources/distances_dso.csv) for named objects
  where the systematic tiers give a bad answer: Local Group galaxies (where
  peculiar velocity dominates the Hubble-law estimate from redshift) and a
  few well-known nebulae OpenNGC has no Pax/Redshift for at all. Keyed by
  catalogue id (e.g. "M101", "NGC6888") or, for objects with no catalogue
  number (most Local Group dwarfs), the object's literal `name` string.

See cat_enhancements.md for the full investigation and sourcing notes.
"""

import csv
from pathlib import Path
from typing import Any


def parse_harris_catalog(path: Path) -> dict[int, float]:
    """Parse Harris's Part I table and return {ngc_number: dist_pc}."""
    lines = path.read_text(encoding="utf-8").splitlines()
    header_idx = next(
        (i for i, line in enumerate(lines) if line.strip().startswith("ID") and "R_Sun" in line),
        None,
    )
    if header_idx is None:
        return {}
    result: dict[int, float] = {}
    for line in lines[header_idx + 1 :]:
        if not line.strip():
            continue
        if line.strip().startswith("___"):
            break
        object_id = line[1:12].strip()
        if not object_id.startswith("NGC"):
            continue
        try:
            ngc_number = int(object_id[3:].strip())
        except ValueError:
            continue
        # Columns 1-24 are the (variable-width, space-containing) ID and Name
        # fields - skip past both via fixed-width slicing rather than
        # `.split()`, which would misalign on rows with a Name value (e.g.
        # "NGC 104    47 Tuc ...") by picking up its tokens as RA/Dec pieces.
        fields = line[50:].split()  # L, B, R_Sun, R_gc, X, Y, Z
        if len(fields) < 3:
            continue
        try:
            r_sun_kpc = float(fields[2])
        except ValueError:
            continue
        result[ngc_number] = r_sun_kpc * 1000.0
    return result


def load_distance_overrides(sources_dir: Path) -> dict[str, float]:
    """Load the hand-curated id/name -> dist_pc overrides."""
    path = sources_dir / "distances_dso.csv"
    if not path.exists():
        return {}
    overrides: dict[str, float] = {}
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            key = row.get("id", "").strip()
            dist_raw = row.get("dist_pc", "").strip()
            if not key or not dist_raw:
                continue
            try:
                overrides[key] = float(dist_raw)
            except ValueError:
                continue
    return overrides


def _catalogue_id(obj: dict[str, Any]) -> str | None:
    """Reconstruct the same M > NGC > IC > Caldwell id used client-side."""
    if "m" in obj:
        return f"M{obj['m']}"
    if "ngc" in obj:
        return f"NGC{obj['ngc']}"
    if "ic" in obj:
        return f"IC{obj['ic']}"
    if "cald" in obj:
        return f"C{obj['cald']}"
    return None


def apply_distance_overrides(
    objects: list[dict[str, Any]],
    harris_by_ngc: dict[int, float],
    overrides: dict[str, float],
) -> None:
    """Fill/override `dist` (parsecs) on matching objects, in place."""
    for obj in objects:
        if obj.get("type") == "globular cluster" and "ngc" in obj:
            dist = harris_by_ngc.get(obj["ngc"])
            if dist is not None:
                obj["dist"] = dist
                continue
        catalogue_id = _catalogue_id(obj)
        if catalogue_id is not None and catalogue_id in overrides:
            obj["dist"] = overrides[catalogue_id]
        elif obj.get("name") in overrides:
            obj["dist"] = overrides[obj["name"]]
