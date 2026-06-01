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
        self._debug = bool(debug)

    def attach(
        self,
        stars: list[dict[str, Any]],
        max_mag: float,
        min_sep: float,
    ) -> tuple[int, int]:
        """Attach double-star metadata under `dbl`; return (stars_with_dbl, pair_count)."""
        tsv_path = self._downloader.fetch(WDS_VIZIER_URL, WDS_FILENAME)
        systems = self._load_systems(tsv_path, max_mag=max_mag, min_sep=min_sep)

        # Try to load and merge ORB6 periods (non-fatal)
        orb_map: dict[str, float] = {}
        try:
            orb_path = self._downloader.fetch(ORB6_VIZIER_URL, ORB6_FILENAME)
            orb_map = self._load_orb_periods(orb_path)
        except OSError:
            orb_map = {}

        if orb_map:
            self._merge_orb_periods_into_systems(systems, orb_map)

        stars_with_hip = [s for s in stars if isinstance(s.get("hip"), int)]
        if not stars_with_hip:
            return 0, 0

        return self._apply_systems_to_stars(systems, stars_with_hip)

    def _merge_orb_periods_into_systems(
        self,
        systems: list[dict[str, Any]],
        orb_map: dict[str, float],
    ) -> None:
        """Attach orbital periods from `orb_map` into system pairs in-place."""
        for system in systems:
            period = orb_map.get(system["wds"])
            if period is None:
                continue
            for pair in system.get("pairs", []):
                pair["period"] = period

    def _apply_systems_to_stars(
        self,
        systems: list[dict[str, Any]],
        stars_with_hip: list[dict[str, Any]],
    ) -> tuple[int, int]:
        """Match systems to stars, attach `dbl` payloads, and return counts."""
        # Build a simple RA/Dec bin index to avoid O(N*M) full scans when
        # matching systems to stars. Use 1-degree declination bins and 1-hour
        # RA bins (hours) as a cheap spatial index; this is sufficient given
        # the small matching radius (0.2 degrees) used by `_match_system_star`.
        bins: dict[tuple[int, int], list[dict[str, Any]]] = {}
        for s in stars_with_hip:
            ra_h, dec_d = s["pos"]
            ra_bin = int(ra_h) % 24
            dec_bin = int(dec_d)
            bins.setdefault((ra_bin, dec_bin), []).append(s)

        def _candidate_stars(sys_ra: float, sys_dec: float) -> list[dict[str, Any]]:
            ra_bin = int(sys_ra) % 24
            dec_bin = int(sys_dec)
            cand: list[dict[str, Any]] = []
            # search neighbouring bins within +/-1 in both coordinates
            for r in (ra_bin - 1, ra_bin, ra_bin + 1):
                rb = r % 24
                for d in (dec_bin - 1, dec_bin, dec_bin + 1):
                    key = (rb, d)
                    if key in bins:
                        cand.extend(bins[key])
            return cand

        pair_count = 0
        touched: set[int] = set()
        for system in systems:
            sys_ra, sys_dec = system["pos"]
            candidates = _candidate_stars(sys_ra, sys_dec)
            if not candidates:
                continue
            # Find the best match among candidates only.
            best: tuple[float, dict[str, Any]] | None = None
            for star in candidates:
                ra, dec = star["pos"]
                dist = _angular_distance_deg(sys_ra, sys_dec, ra, dec)
                if best is None or dist < best[0]:
                    best = (dist, star)
            if best is None:
                continue
            distance, matched = best
            if distance > 0.2:
                continue
            # Magnitude-consistency check: if the matched star has a magnitude
            # recorded, ensure it reasonably matches one of the pair magnitudes
            # in the system to reduce false attachments. If no mag is present
            # on the star, accept the match.
            star_mag = matched.get("mag")
            def _star_mag_value(m):
                if isinstance(m, (int, float)):
                    return float(m)
                if isinstance(m, list) and m:
                    # variable encoding as [min, max] → use midpoint
                    return float((m[0] + m[-1]) / 2.0)
                return None

            s_val = _star_mag_value(star_mag)
            attach_ok = True
            if s_val is not None:
                attach_ok = False
                # check each pair's component magnitudes for a near match
                for pair in system.get("pairs", []):
                    mags = pair.get("mag") or []
                    for pm in mags:
                        try:
                            pmf = float(pm)
                        except Exception:
                            continue
                        if abs(s_val - pmf) <= 1.0:  # 1 mag tolerance
                            attach_ok = True
                            break
                    if attach_ok:
                        break
                if not attach_ok and self._debug:
                    print(
                        f"Skipping attach for system {system['wds']} -> star hip={matched.get('hip')}"
                        f" due to magnitude mismatch (star={s_val}, pairs={[p.get('mag') for p in system.get('pairs',[])]})"
                    )
            if not attach_ok:
                continue
            pair_count += self._attach_payload_and_count(matched, system, touched)
        return len(touched), pair_count

    @staticmethod
    def _build_payload(system: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "wds": system["wds"],
            "disc": system.get("disc"),
            "pairs": system["pairs"],
        }
        if payload["disc"] is None:
            payload.pop("disc")
        return payload

    def _attach_payload_and_count(
        self,
        matched: dict[str, Any],
        system: dict[str, Any],
        touched: set[int],
    ) -> int:
        """Attach payload to matched star, update `touched`, and return number of pairs added."""
        payload = self._build_payload(system)
        matched.setdefault("dbl", []).append(payload)
        hip = matched.get("hip")
        if isinstance(hip, int):
            touched.add(hip)
        return len(system.get("pairs", []))

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
                    system = self._init_system_from_row(wds_id, row, ra, dec)
                    grouped[wds_id] = system

                pair = self._build_pair_from_row(row, mag1, mag2, sep1, sep2)
                system["pairs"].append(pair)
                system["_score"] = max(system["_score"], 20.0 - (mag1 + mag2))

        systems = sorted(grouped.values(), key=lambda s: s["_score"], reverse=True)
        for system in systems:
            system.pop("_score", None)
        return systems

    def _init_system_from_row(
        self,
        wds_id: str,
        row: dict[str, Any],
        ra: float,
        dec: float,
    ) -> dict[str, Any]:
        """Create initial system dict for a WDS id from a TSV row."""
        return {
            "wds": wds_id,
            "disc": row.get("Disc", "").strip() or None,
            "pos": [ra, dec],
            "pairs": [],
            "_score": -1e9,
        }

    def _build_pair_from_row(
        self,
        row: dict[str, Any],
        mag1: float,
        mag2: float,
        sep1: float | None,
        sep2: float | None,
    ) -> dict[str, Any]:
        """Build a pair payload from a TSV row and parsed magnitudes/separations."""
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
            pair["vis"] = pair["comp"]
        return pair

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
