"""Curated dark-nebula supplement for dso.json.

OpenNGC (the source for dso.py) catalogues no dark nebulae at all - they're
mostly Barnard-numbered objects without their own NGC/IC identifier, so they
were never in scope for that project. Dark nebulae also aren't selectable by
the usual magnitude filter (they have none - visibility is about contrast
against a star field, not brightness). Rather than invent a size/opacity
threshold, this is a small hand-picked list of well-known objects confirmed
visible in <=8" telescopes, with positions/sizes sourced from SIMBAD. See
cat_enhancements.md for the selection rationale and per-object sourcing.
"""

import csv
from pathlib import Path
from typing import Any


def _size(maj: str, minor: str) -> float | list[float]:
    maj_val = float(maj)
    min_val = float(minor) if minor.strip() else maj_val
    if min_val == maj_val:
        return maj_val
    return [maj_val, min_val]


def _build_dark_nebula(row: dict[str, str]) -> dict[str, Any]:
    return {
        "pos": [float(row["ra_hours"]), float(row["dec_deg"])],
        "type": "dark nebula",
        "name": row["name"],
        "size": _size(row["size_maj"], row["size_min"]),
        "const": row["const"],
    }


def load_dark_nebulae(sources_dir: Path) -> list[dict[str, Any]]:
    """Load the curated dark-nebula CSV and return DSO-shaped objects."""
    path = sources_dir / "dark_nebulae.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return [_build_dark_nebula(row) for row in reader]
