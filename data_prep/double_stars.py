"""Double-star helper: WDS TSV -> per-star double metadata annotations."""

# pylint: disable=duplicate-code

import csv
import math
from pathlib import Path
from typing import Any

from config import ORB6_FILENAME, ORB6_VIZIER_URL, WDS_FILENAME, WDS_VIZIER_URL
from downloader import Downloader


def _float_or_none(value: str) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _ra_hours(raw: str) -> float | None:
    """Parse VizieR WDS RA string 'hh mm ss.ss' to decimal hours."""
    parts = raw.split()
    if len(parts) != 3:
        return None
    h = _float_or_none(parts[0])
    m = _float_or_none(parts[1])
    s = _float_or_none(parts[2])
    if h is None or m is None or s is None:
        return None
    return h + m / 60.0 + s / 3600.0


def _dec_degrees(raw: str) -> float | None:
    """Parse VizieR WDS Dec string '+dd mm ss.s' to decimal degrees."""
    parts = raw.split()
    if len(parts) != 3:
        return None
    sign = -1.0 if raw.startswith("-") else 1.0
    d = _float_or_none(parts[0].lstrip("+-"))
    m = _float_or_none(parts[1])
    s = _float_or_none(parts[2])
    if d is None or m is None or s is None:
        return None
    return sign * (d + m / 60.0 + s / 3600.0)


def _sep_value(sep1: float | None, sep2: float | None) -> float | None:
    """Current separation proxy for filtering/ranking, preferring latest value."""
    return sep2 if sep2 is not None else sep1


def _sep_range(sep1: float | None, sep2: float | None) -> float | list[float] | None:
    """Return separation as scalar or [min, max] when both measurements exist."""
    if sep1 is None and sep2 is None:
        return None
    if sep1 is None:
        return sep2
    if sep2 is None:
        return sep1
    return [min(sep1, sep2), max(sep1, sep2)]


def _is_physical(notes: str) -> bool | None:
    """Map WDS notes to physical/optical where hinted; otherwise None."""
    note = notes.strip().upper()
    if not note:
        return None
    if "P" in note:
        return True
    if "O" in note:
        return False
    return None


def _angular_distance_deg(ra1_h: float, dec1_d: float, ra2_h: float, dec2_d: float) -> float:
    """Great-circle distance in degrees between two equatorial points."""
    ra1 = math.radians(ra1_h * 15.0)
    ra2 = math.radians(ra2_h * 15.0)
    dec1 = math.radians(dec1_d)
    dec2 = math.radians(dec2_d)
    cos_d = (
        math.sin(dec1) * math.sin(dec2)
        + math.cos(dec1) * math.cos(dec2) * math.cos(ra1 - ra2)
    )
    cos_d = max(-1.0, min(1.0, cos_d))
    return math.degrees(math.acos(cos_d))


class DoubleStarMatcher:
    """Load WDS data and attach double-star metadata to star objects by HIP."""

    def __init__(
        self,
        sources_dir: Path,
        cache_dir: Path | None = None,
        debug: bool = False,
    ) -> None:
        self._sources_dir = sources_dir
        cache = cache_dir or sources_dir
        self._downloader = Downloader(cache, debug=debug)

    def attach(
        self,
        stars: list[dict[str, Any]],
        max_mag: float,
        min_sep: float,
    ) -> tuple[int, int]:
        """Attach double-star metadata under `dbl`; return (stars_with_dbl, pair_count)."""
        tsv_path = self._downloader.fetch(WDS_VIZIER_URL, WDS_FILENAME)
        systems = self._load_systems(tsv_path, max_mag=max_mag, min_sep=min_sep)
        # Try to fetch ORB6 orbital periods and map them by WDS id.
        orb_map: dict[str, float] = {}
        try:
            orb_path = self._downloader.fetch(ORB6_VIZIER_URL, ORB6_FILENAME)
            orb_map = self._load_orb_periods(orb_path)
        except OSError:
            # Non-fatal: if ORB6 fetch fails (network/file error), continue
            # without periods.
            orb_map = {}
        # Merge periods into systems' pairs when available.
        if orb_map:
            for system in systems:
                period = orb_map.get(system["wds"])
                if period is None:
                    continue
                # Attach period to all pairs in the system where applicable.
                for pair in system.get("pairs", []):
                    pair["period"] = period
        stars_with_hip = [s for s in stars if isinstance(s.get("hip"), int)]
        if not stars_with_hip:
            return 0, 0

        pair_count = 0
        touched: set[int] = set()
        for system in systems:
            matched = self._match_system_star(system, stars_with_hip)
            if matched is None:
                continue
            payload = {
                "wds": system["wds"],
                "disc": system.get("disc"),
                "pairs": system["pairs"],
            }
            if payload["disc"] is None:
                payload.pop("disc")
            matched.setdefault("dbl", []).append(payload)
            touched.add(matched["hip"])
            pair_count += len(system["pairs"])
        return len(touched), pair_count

    def _load_systems(self, tsv_path: Path, max_mag: float, min_sep: float) -> list[dict[str, Any]]:
        # pylint: disable=too-many-locals
        grouped: dict[str, dict[str, Any]] = {}
        with tsv_path.open(encoding="utf-8") as fh:
            reader = csv.DictReader(self._iter_data_lines(fh), delimiter="\t")
            for row in reader:
                mag1 = _float_or_none(row.get("mag1", ""))
                mag2 = _float_or_none(row.get("mag2", ""))
                sep1 = _float_or_none(row.get("sep1", ""))
                sep2 = _float_or_none(row.get("sep2", ""))
                sep = _sep_value(sep1, sep2)
                if mag1 is None or mag2 is None or sep is None:
                    continue
                if mag1 > max_mag or mag2 > max_mag:
                    continue
                if sep < min_sep or sep > 60.0:
                    continue

                wds_id = row.get("WDS", "").strip()
                ra = _ra_hours(row.get("RAJ2000", ""))
                dec = _dec_degrees(row.get("DEJ2000", ""))
                if not wds_id or ra is None or dec is None:
                    continue

                system = grouped.get(wds_id)
                if system is None:
                    system = {
                        "wds": wds_id,
                        "disc": row.get("Disc", "").strip() or None,
                        "pos": [ra, dec],
                        "pairs": [],
                        "_score": -1e9,
                    }
                    grouped[wds_id] = system

                pair: dict[str, Any] = {
                    "comp": row.get("Comp", "").strip() or "AB",
                    "mag": [mag1, mag2],
                }
                sep_payload = _sep_range(sep1, sep2)
                if sep_payload is not None:
                    pair["sep"] = sep_payload
                phys_flag = _is_physical(row.get("Notes", ""))
                if phys_flag is True:
                    pair["phys"] = pair["comp"]
                elif phys_flag is False:
                    # Explicitly mark known non-physical (visual/optical)
                    # pairs using `vis` so callers can distinguish.
                    pair["vis"] = pair["comp"]
                system["pairs"].append(pair)
                system["_score"] = max(system["_score"], 20.0 - (mag1 + mag2))

        systems = sorted(grouped.values(), key=lambda s: s["_score"], reverse=True)
        for system in systems:
            system.pop("_score", None)
        return systems

    @staticmethod
    def _load_orb_periods(tsv_path: Path) -> dict[str, float]:
        """Load ORB6 master table TSV and return mapping WDS -> period (years)."""
        mapping: dict[str, float] = {}
        with tsv_path.open(encoding="utf-8") as fh:
            # Avoid single-letter loop variable flagged by linter.
            reader = csv.DictReader(
                (line for line in fh if not line.startswith("#")), delimiter="\t"
            )
            for row in reader:
                wds = row.get("WDS", "").strip()
                p = _float_or_none(row.get("P", ""))
                if not wds or p is None:
                    continue
                mapping[wds] = p
        return mapping

    @staticmethod
    def _match_system_star(
        system: dict[str, Any],
        stars: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Return nearest star candidate for one WDS system if reasonably close."""
        best: tuple[float, dict[str, Any]] | None = None
        sys_ra, sys_dec = system["pos"]
        for star in stars:
            ra, dec = star["pos"]
            dist = _angular_distance_deg(sys_ra, sys_dec, ra, dec)
            if best is None:
                best = (dist, star)
                continue
            best_distance, _ = best
            if dist < best_distance:
                best = (dist, star)
        if best is None:
            return None
        distance, matched = best
        if distance > 0.2:
            return None
        return matched

    @staticmethod
    def _iter_data_lines(lines: Any) -> Any:
        """Yield only table lines from VizieR TSV response."""
        started = False
        for line in lines:
            if line.startswith("#") or not line.strip():
                continue
            if not started and line.startswith("WDS\t"):
                started = True
                yield line
                continue
            if not started:
                continue
            if line.startswith("----------"):
                continue
            yield line
