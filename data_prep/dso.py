"""Deep-sky object pipeline: OpenNGC CSV -> data_prep/output/dso.json."""

import csv
import json
import re
from pathlib import Path
from typing import Any

from config import (
    DSO_ADDENDUM_FILENAME,
    DSO_ADDENDUM_URL,
    DSO_MAIN_FILENAME,
    DSO_MAIN_URL,
    DSO_MAX_MAG,
    EUROPE_MIN_DEC,
    HARRIS_GC_FILENAME,
    HARRIS_GC_URL,
    HUBBLE_CONSTANT_KM_S_MPC,
    SPEED_OF_LIGHT_KM_S,
)
from dark_nebulae import load_dark_nebulae
from distances import apply_distance_overrides, load_distance_overrides, parse_harris_catalog
from downloader import Downloader

_TYPE_MAP: dict[str, str] = {
    "OCl": "open cluster",
    "OC": "open cluster",
    "GCl": "globular cluster",
    "GC": "globular cluster",
    "PN": "planetary nebula",
    "Neb": "emission nebula",
    "EN": "emission nebula",
    "HII": "emission nebula",
    "RfN": "reflection nebula",
    "RN": "reflection nebula",
    "DNe": "dark nebula",
    "DN": "dark nebula",
}

_CATALOGUE_NAME_PATTERN = re.compile(r"^(NGC|IC)0*([1-9][0-9]*)$")
_CALDWELL_PATTERN = re.compile(r"\bC\s*0*([1-9][0-9]{0,2})\b")
_NAME_OVERRIDES: dict[str, str] = {
    "NGC225": "Sailboat Cluster",
}


def _float_or_none(value: str) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _ra_hours(raw: str) -> float | None:
    """Parse RA from HH:MM:SS.s to decimal hours."""
    parts = raw.split(":")
    if len(parts) != 3:
        return None
    h = _float_or_none(parts[0])
    m = _float_or_none(parts[1])
    s = _float_or_none(parts[2])
    if h is None or m is None or s is None:
        return None
    return h + (m / 60.0) + (s / 3600.0)


def _dec_degrees(raw: str) -> float | None:
    """Parse Dec from [+/-]DD:MM:SS.s to decimal degrees."""
    parts = raw.split(":")
    if len(parts) != 3:
        return None
    sign = -1.0 if raw.startswith("-") else 1.0
    d = _float_or_none(parts[0].lstrip("+-"))
    m = _float_or_none(parts[1])
    s = _float_or_none(parts[2])
    if d is None or m is None or s is None:
        return None
    return sign * (d + (m / 60.0) + (s / 3600.0))


def _messier_id(raw: str) -> str | None:
    if not raw:
        return None
    try:
        return f"M{int(raw)}"
    except ValueError:
        return None


def _catalogue_id(row: dict[str, str]) -> str:
    messier = _messier_id(row.get("M", ""))
    if messier:
        return messier

    ngc_value = row.get("NGC", "")
    if ngc_value:
        prefix = "NGC"
        raw_value = ngc_value
    else:
        ic_value = row.get("IC", "")
        if ic_value:
            prefix = "IC"
            raw_value = ic_value
        else:
            name = row.get("Name", "")
            match = _CATALOGUE_NAME_PATTERN.match(name)
            if not match:
                return name
            prefix = match.group(1)
            raw_value = match.group(2)

    try:
        number = int(raw_value)
        return f"{prefix}{number}"
    except ValueError:
        return f"{prefix}{raw_value}"


def _caldwell_id(row: dict[str, str]) -> str | None:
    """Return Caldwell catalogue id (e.g. C13) when present in identifiers."""
    identifiers = row.get("Identifiers", "")
    match = _CALDWELL_PATTERN.search(identifiers)
    if not match:
        return None
    return f"C{int(match.group(1))}"


def _caldwell_num(row: dict[str, str]) -> int | None:
    """Return Caldwell catalogue number (e.g. 13) when present."""
    caldwell = _caldwell_id(row)
    if caldwell is None:
        return None
    return int(caldwell[1:])


def _is_large_diffuse(type_code: str, maj_ax: float | None) -> bool:
    """Return True for diffuse nebulae that are too large for this catalogue."""
    return type_code in {"EN", "RN", "DN", "Neb", "RfN", "HII", "DNe"} and (
        maj_ax is not None and maj_ax > 60.0
    )


def _type_label(type_code: str, hubble: str) -> str | None:
    """Map OpenNGC type codes to the app vocabulary."""
    if type_code == "G":
        morph = hubble.upper().strip()
        if morph.startswith("E"):
            return "elliptical galaxy"
        if morph.startswith("S") or morph.startswith("SB"):
            return "spiral galaxy"
        return "galaxy"
    return _TYPE_MAP.get(type_code)


def _messier_fallback_type(type_code: str) -> str | None:
    """Fallback type mapping for uncommon Messier classifications."""
    return {
        "SNR": "emission nebula",
        "Cl+N": "emission nebula",
        "*Ass": "open cluster",
        "Other": "open cluster",
    }.get(type_code)


def _rank_mag(row: dict[str, str]) -> float | None:
    """Ranking magnitude for non-Messier selection."""
    return _float_or_none(row.get("V-Mag", "")) or _float_or_none(row.get("B-Mag", ""))


# Types with a discrete point source (central star / dominant cluster stars)
# whose compiled parallax is a reasonable distance estimate. Globular
# clusters are deliberately excluded - see distances.py's module docstring.
_PARALLAX_DISTANCE_TYPES: frozenset[str] = frozenset(
    {"planetary nebula", "open cluster", "emission nebula", "reflection nebula"}
)
_GALAXY_TYPES: frozenset[str] = frozenset({"spiral galaxy", "elliptical galaxy", "galaxy"})


def _distance_from_parallax_pc(pax_mas: float) -> float | None:
    """Distance in parsecs from a parallax in milliarcseconds."""
    if pax_mas <= 0:
        return None
    return 1000.0 / pax_mas


def _distance_from_redshift_pc(redshift: float) -> float | None:
    """Hubble-law distance estimate in parsecs from a redshift value.

    Approximate by design (ignores peculiar velocity) - wrong for Local
    Group members, which get a curated override instead (see distances.py).
    """
    if redshift <= 0:
        return None
    dist_mpc = (redshift * SPEED_OF_LIGHT_KM_S) / HUBBLE_CONSTANT_KM_S_MPC
    return dist_mpc * 1_000_000.0


def _dso_distance_pc(obj_type: str, row: dict[str, str]) -> float | None:
    """Tiered distance in parsecs for one OpenNGC row (see cat_enhancements.md)."""
    if obj_type in _GALAXY_TYPES:
        redshift = _float_or_none(row.get("Redshift", ""))
        return _distance_from_redshift_pc(redshift) if redshift is not None else None
    if obj_type in _PARALLAX_DISTANCE_TYPES:
        pax = _float_or_none(row.get("Pax", ""))
        return _distance_from_parallax_pc(pax) if pax is not None else None
    return None


def _load_notes(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    notes: dict[str, str] = {}
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            object_id = row.get("id", "").strip().upper()
            note = row.get("note", "").strip()
            if object_id and note:
                notes[object_id] = note
    return notes


def _catalogue_numbers(row: dict[str, str]) -> dict[str, int]:
    """Return available numeric catalogue fields from one source row."""
    numbers: dict[str, int] = {}
    m_raw = row.get("M", "")
    if m_raw:
        try:
            numbers["m"] = int(m_raw)
        except ValueError:
            pass
    ngc_raw = row.get("NGC", "")
    if ngc_raw:
        try:
            numbers["ngc"] = int(ngc_raw)
        except ValueError:
            pass
    ic_raw = row.get("IC", "")
    if ic_raw:
        try:
            numbers["ic"] = int(ic_raw)
        except ValueError:
            pass
    if "ngc" not in numbers and "ic" not in numbers:
        match = _CATALOGUE_NAME_PATTERN.match(row.get("Name", ""))
        if match:
            numbers[match.group(1).lower()] = int(match.group(2))
    cald = _caldwell_num(row)
    if cald is not None:
        numbers["cald"] = cald
    return numbers


def _object_sort_key(item: dict[str, Any]) -> tuple[int, int, int, int]:
    """Deterministic sort key preferring major catalogue identifiers."""
    return (
        item.get("m", 1_000_000),
        item.get("ngc", 1_000_000),
        item.get("ic", 1_000_000),
        item.get("cald", 1_000_000),
    )


def _build_dso(row: dict[str, str], note: str | None) -> dict[str, Any] | None:
    """Build one output DSO object, omitting absent fields."""
    ra = _ra_hours(row.get("RA", ""))
    dec = _dec_degrees(row.get("Dec", ""))
    if ra is None or dec is None or dec < EUROPE_MIN_DEC:
        return None
    obj_type = _type_label(row.get("Type", ""), row.get("Hubble", ""))
    if obj_type is None and _messier_id(row.get("M", "")):
        obj_type = _messier_fallback_type(row.get("Type", ""))
    if obj_type is None:
        return None

    obj_id = _catalogue_id(row)
    raw_name = row.get("Common names", "") or None
    name = raw_name or _NAME_OVERRIDES.get(obj_id)
    obj: dict[str, Any] = {
        "pos": [ra, dec],
        "type": obj_type,
        "const": row.get("Const", "") or None,
    }
    obj.update(_catalogue_numbers(row))
    for key, value in (
        ("name", name),
        ("mag", _rank_mag(row)),
        ("size", _size_pair(row)),
        ("ang", _float_or_none(row.get("PosAng", ""))),
        ("cstar_mag", _float_or_none(row.get("Cstar V-Mag", ""))),
        ("dist", _dso_distance_pc(obj_type, row)),
        ("note", note),
    ):
        if value is not None:
            obj[key] = value
    return obj


def _size_pair(row: dict[str, str]) -> float | list[float] | None:
    major = _float_or_none(row.get("MajAx", ""))
    minor = _float_or_none(row.get("MinAx", ""))
    if major is None:
        return None
    if minor is None or major == minor:
        return major
    return [major, minor]


class DsoPipeline:
    """Download OpenNGC, select target objects, and write dso.json."""

    def __init__(
        self,
        sources_dir: Path,
        output_dir: Path,
        cache_dir: Path | None = None,
        dso_mag_limit: float = DSO_MAX_MAG,
        debug: bool = False,
    ) -> None:
        self._sources_dir = sources_dir
        self._output_dir = output_dir
        self._dso_mag_limit = dso_mag_limit
        cache = cache_dir or sources_dir
        self._downloader = Downloader(cache, debug=debug)

    def run(self, object_id: str | None = None) -> Path:
        """Execute full DSO pipeline and return output file path."""
        csv_paths = [
            self._downloader.fetch(DSO_MAIN_URL, DSO_MAIN_FILENAME),
            self._downloader.fetch(DSO_ADDENDUM_URL, DSO_ADDENDUM_FILENAME),
        ]
        notes = _load_notes(self._sources_dir / "notes_dso.csv")
        objects = self._process(csv_paths, notes, object_id)
        if object_id is None:
            objects = objects + load_dark_nebulae(self._sources_dir)
            harris_path = self._downloader.fetch(HARRIS_GC_URL, HARRIS_GC_FILENAME)
            harris_by_ngc = parse_harris_catalog(harris_path)
            overrides = load_distance_overrides(self._sources_dir)
            apply_distance_overrides(objects, harris_by_ngc, overrides)
        return self._write(objects)

    def _process(
        self,
        csv_paths: list[Path],
        notes: dict[str, str],
        object_id: str | None,
    ) -> list[dict[str, Any]]:
        """Select Messier plus brightest non-Messier objects and build output rows."""
        selected = self._select_rows(csv_paths, object_id)
        objects: list[dict[str, Any]] = []
        for row in selected:
            obj_id = _catalogue_id(row).upper()
            built = _build_dso(row, notes.get(obj_id))
            if built is not None:
                objects.append(built)
        objects.sort(key=_object_sort_key)
        return objects

    def _select_rows(
        self,
        csv_paths: list[Path],
        object_id: str | None,
    ) -> list[dict[str, str]]:
        rows = self._read_rows(csv_paths)
        if object_id:
            wanted = object_id.strip().upper()
            return [r for r in rows if _catalogue_id(r).upper() == wanted]

        messier = [r for r in rows if _messier_id(r.get("M", ""))]
        non_messier = self._non_messier_by_mag(rows)
        return messier + non_messier

    def _non_messier_by_mag(self, rows: list[dict[str, str]]) -> list[dict[str, str]]:
        result: list[dict[str, str]] = []
        for row in rows:
            if _messier_id(row.get("M", "")):
                continue
            maj_ax = _float_or_none(row.get("MajAx", ""))
            if _is_large_diffuse(row.get("Type", ""), maj_ax):
                continue
            if _type_label(row.get("Type", ""), row.get("Hubble", "")) is None:
                continue
            ra = _ra_hours(row.get("RA", ""))
            dec = _dec_degrees(row.get("Dec", ""))
            if ra is None or dec is None or dec < EUROPE_MIN_DEC:
                continue
            mag = _rank_mag(row)
            if mag is None or mag > self._dso_mag_limit:
                continue
            result.append(row)
        return result

    def _read_rows(self, csv_paths: list[Path]) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        seen: set[str] = set()
        for csv_path in csv_paths:
            with csv_path.open(encoding="utf-8") as fh:
                reader = csv.DictReader(fh, delimiter=";")
                for row in reader:
                    key = row.get("Name", "")
                    if key and key not in seen:
                        rows.append(row)
                        seen.add(key)
        return rows

    def _write(self, objects: list[dict[str, Any]]) -> Path:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        out = self._output_dir / "dso.json"
        grouped: dict[str, list[dict[str, Any]]] = {}
        for obj in objects:
            key = obj.pop("const", None) or "NO_CONST"
            grouped.setdefault(key, []).append(obj)
        for con_objects in grouped.values():
            con_objects.sort(key=_object_sort_key)
        with out.open("w", encoding="utf-8") as fh:
            json.dump(grouped, fh, ensure_ascii=False)
        n_notes = sum(1 for obj in objects if "note" in obj)
        n_dark = sum(1 for obj in objects if obj.get("type") == "dark nebula")
        n_dist = sum(1 for obj in objects if obj.get("dist") is not None)
        print(f"DSO included   : {len(objects):,}")
        print(f"Dark nebulae   : {n_dark} curated" if n_dark else "Dark nebulae   : none")
        print(f"DSO distances  : {n_dist:,} of {len(objects):,}")
        print(f"DSO notes      : {n_notes} curated" if n_notes else "DSO notes      : none")
        print(f"Output         : {out} ({out.stat().st_size / 1_048_576:.2f} MB)")
        return out
