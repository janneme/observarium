"""Double-star helper: WDS TSV -> per-star double metadata annotations."""

# pylint: disable=duplicate-code

import csv
import math
import re
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
    """Map WDS notes to physical/optical where hinted; otherwise None.

    WDS Notes column characters (relevant subset):
      P = physical pair (common proper motion / parallax confirmed)
      O = orbital solution exists — also proves a physical pair
    There is no explicit "optical" code; apparent pairs are identified
    by classify_apparent_pairs() using parallax distances instead.
    """
    note = notes.strip().upper()
    if not note:
        return None
    if "P" in note or "O" in note:
        return True
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


_PC_TO_AU: float = 206_265.0  # 1 parsec in AU
_APPARENT_PAIR_SEP_MATCH_TOL_ARCSEC: float = 3.0


def _angular_sep_arcsec(pos1: list[float], pos2: list[float]) -> float:
    """Angular separation in arcseconds between two [ra_h, dec_d] positions."""
    ra1, de1 = pos1
    ra2, de2 = pos2
    dra = (ra2 - ra1) * 15.0 * math.cos(math.radians((de1 + de2) / 2.0))
    dde = de2 - de1
    return math.hypot(dra, dde) * 3600.0


def _normalize_spect(spect: str) -> str:
    """Normalize spectral separators and whitespace for display/storage."""
    if not spect:
        return ""
    normalized = spect.replace("+", "/")
    normalized = re.sub(r"\s*/\s*", " / ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _is_composite_spect(spect: str) -> bool:
    """Return True if spectral text appears to encode multiple components."""
    return " / " in _normalize_spect(spect)


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
    ) -> tuple[int, int, int]:
        """Attach double-star metadata under `dbl`.

        Returns (stars_with_dbl, pair_count, phys_count).
        """
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
            return 0, 0, 0

        return self._apply_systems_to_stars(systems, stars_with_hip, stars)

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
                pair.setdefault("phys", pair["comp"])

    def _resolve_system_match(
        self,
        system: dict[str, Any],
        stars_with_hip: list[dict[str, Any]],
        bins: dict[tuple[int, int], list[dict[str, Any]]],
    ) -> dict[str, Any] | None:
        """Return the star matched to *system* — direct match, else the
        nearest bin candidate within 0.2°, else None."""
        matched = self._find_direct_match(system, stars_with_hip)
        if matched is not None:
            return matched
        sys_ra, sys_dec = system["pos"]
        candidates = self._get_bin_candidates(sys_ra, sys_dec, bins)
        if not candidates:
            return None
        nearest = self._find_nearest(candidates, sys_ra, sys_dec)
        if nearest is None:
            return None
        dist, matched = nearest
        if dist > 0.2:
            return None
        return matched

    def _apply_systems_to_stars(
        self,
        systems: list[dict[str, Any]],
        stars_with_hip: list[dict[str, Any]],
        all_stars: list[dict[str, Any]],
    ) -> tuple[int, int, int]:
        """Match systems to stars, attach `dbl` payloads, and return counts."""
        bins = self._build_spatial_bins(stars_with_hip)
        all_bins = self._build_spatial_bins([s for s in all_stars if s.get("pos")])
        pair_count = 0
        phys_count = 0
        touched: set[int] = set()
        for system in systems:
            matched = self._resolve_system_match(system, stars_with_hip, bins)
            if matched is None:
                continue
            if not self._passes_mag_check(matched, system):
                continue
            self._enrich_system_spect_from_components(system, matched, all_bins)
            pair_count += self._attach_payload_and_count(matched, system, touched)
            phys_count += sum(1 for p in system.get("pairs", []) if "phys" in p)
        return len(touched), pair_count, phys_count

    def _enrich_system_spect_from_components(
        self,
        system: dict[str, Any],
        matched: dict[str, Any],
        bins: dict[tuple[int, int], list[dict[str, Any]]],
    ) -> None:
        """Fill system spect as primary/secondary when only a single type is known."""
        current = system.get("spect", "") or ""
        if _is_composite_spect(current):
            return
        primary = _normalize_spect(current or (matched.get("spect") or ""))
        if not primary:
            return
        secondary = self._infer_secondary_spect(system, matched, bins)
        if not secondary:
            return
        if _normalize_spect(secondary).upper() == primary.upper():
            return
        system["spect"] = f"{primary} / {_normalize_spect(secondary)}"

    def _target_pair_search_params(
        self, system: dict[str, Any], matched: dict[str, Any]
    ) -> tuple[float | None, float] | None:
        """Return (expected_sep, target_mag) to search for a secondary
        component, or None when the AB (or first) pair lacks usable data."""
        pair = next((p for p in system.get("pairs", []) if p.get("comp") == "AB"), None)
        if pair is None:
            pair = (system.get("pairs") or [None])[0]
        if not pair:
            return None
        sep_field = pair.get("sep")
        expected_sep = sep_field[-1] if isinstance(sep_field, list) else sep_field
        pair_mag = pair.get("mag") or []
        if len(pair_mag) < 2:
            return None
        matched_mag = self._mag_to_float(matched.get("mag"))
        m1, m2 = float(pair_mag[0]), float(pair_mag[1])
        target_mag = m2
        if matched_mag is not None and abs(matched_mag - m2) < abs(matched_mag - m1):
            target_mag = m1
        return expected_sep, target_mag

    def _best_secondary_candidate(
        self,
        system: dict[str, Any],
        matched: dict[str, Any],
        bins: dict[tuple[int, int], list[dict[str, Any]]],
        expected_sep: float | None,
        target_mag: float,
    ) -> dict[str, Any] | None:
        """Scan nearby stars for the best-scoring secondary-component match."""
        best_score = math.inf
        best_star: dict[str, Any] | None = None
        cand_stars = self._get_bin_candidates(system["pos"][0], system["pos"][1], bins)
        for cand in cand_stars:
            if cand is matched or not cand.get("spect"):
                continue
            cand_mag = self._mag_to_float(cand.get("mag"))
            if cand_mag is None or abs(cand_mag - target_mag) > 1.0:
                continue
            sep_arc = _angular_sep_arcsec(matched["pos"], cand["pos"])
            if expected_sep is not None:
                tol = max(5.0, float(expected_sep) * 0.35)
                if abs(sep_arc - float(expected_sep)) > tol:
                    continue
                score = abs(sep_arc - float(expected_sep)) + abs(cand_mag - target_mag)
            else:
                score = abs(cand_mag - target_mag)
            if score < best_score:
                best_score = score
                best_star = cand
        return best_star

    def _infer_secondary_spect(
        self,
        system: dict[str, Any],
        matched: dict[str, Any],
        bins: dict[tuple[int, int], list[dict[str, Any]]],
    ) -> str | None:
        """Infer secondary component spectral type from nearby stars."""
        params = self._target_pair_search_params(system, matched)
        if params is None:
            return None
        expected_sep, target_mag = params
        best_star = self._best_secondary_candidate(system, matched, bins, expected_sep, target_mag)
        if best_star is None:
            return None
        return str(best_star.get("spect"))

    @staticmethod
    def _build_payload(system: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "wds": system["wds"],
            "disc": system.get("disc"),
            "pairs": system["pairs"],
        }
        if payload["disc"] is None:
            payload.pop("disc")
        spect = system.get("spect")
        if isinstance(spect, str) and spect.strip():
            payload["spect"] = spect
        return payload

    @staticmethod
    def _prefer_spect(row_spect: str, current_spect: str) -> bool:
        """Return True when row_spect should replace current_spect."""
        if not current_spect:
            return True
        row_composite = _is_composite_spect(row_spect)
        current_composite = _is_composite_spect(current_spect)
        if row_composite and not current_composite:
            return True
        return row_composite == current_composite and len(row_spect) > len(current_spect)

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

    @staticmethod
    def _build_spatial_bins(
        stars: list[dict[str, Any]],
    ) -> dict[tuple[int, int], list[dict[str, Any]]]:
        """Build a 1-hour-RA × 1-degree-Dec bin index for fast spatial lookup."""
        bins: dict[tuple[int, int], list[dict[str, Any]]] = {}
        for s in stars:
            ra_h, dec_d = s["pos"]
            ra_bin = int(ra_h) % 24
            dec_bin = int(dec_d)
            bins.setdefault((ra_bin, dec_bin), []).append(s)
        return bins

    @staticmethod
    def _get_bin_candidates(
        sys_ra: float,
        sys_dec: float,
        bins: dict[tuple[int, int], list[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        """Return stars in the 3×3 bin neighbourhood around (sys_ra, sys_dec)."""
        ra_bin = int(sys_ra) % 24
        dec_bin = int(sys_dec)
        cand: list[dict[str, Any]] = []
        for r in (ra_bin - 1, ra_bin, ra_bin + 1):
            rb = r % 24
            for d in (dec_bin - 1, dec_bin, dec_bin + 1):
                key = (rb, d)
                if key in bins:
                    cand.extend(bins[key])
        return cand

    @staticmethod
    def _find_nearest(
        candidates: list[dict[str, Any]],
        sys_ra: float,
        sys_dec: float,
    ) -> tuple[float, dict[str, Any]] | None:
        """Return (distance_deg, star) for the nearest candidate, or None if empty."""
        best_dist = math.inf
        best_star: dict[str, Any] | None = None
        for star in candidates:
            ra, dec = star["pos"]
            dist = _angular_distance_deg(sys_ra, sys_dec, ra, dec)
            if dist < best_dist:
                best_dist = dist
                best_star = star
        if best_star is None:
            return None
        return (best_dist, best_star)

    @staticmethod
    def _find_direct_match(
        system: dict[str, Any],
        stars: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Return the first star whose HIP or HD id matches the system, or None."""
        sid = system.get("hip")
        if sid is not None:
            for s in stars:
                if s.get("hip") == sid:
                    return s
        hdid = system.get("hd")
        if hdid is not None:
            for s in stars:
                if s.get("hd") == hdid:
                    return s
        return None

    @staticmethod
    def _mag_to_float(m: Any) -> float | None:
        """Convert a magnitude value (scalar or [min, max] list) to float, or None."""
        if isinstance(m, (int, float)):
            return float(m)
        if isinstance(m, list) and m:
            return float((m[0] + m[-1]) / 2.0)
        return None

    def _passes_mag_check(self, matched: dict[str, Any], system: dict[str, Any]) -> bool:
        """Return True if star magnitude is consistent with at least one pair component."""
        s_val = self._mag_to_float(matched.get("mag"))
        if s_val is None:
            return True
        for pair in system.get("pairs", []):
            for pm in (pair.get("mag") or []):
                try:
                    if abs(s_val - float(pm)) <= 1.0:
                        return True
                except (TypeError, ValueError):
                    continue
        if self._debug:
            pair_mags = [pair.get("mag") for pair in system.get("pairs", [])]
            print(
                f"Skipping attach for system {system['wds']} -> "
                f"star hip={matched.get('hip')} due to magnitude mismatch "
                f"(star={s_val}, pairs={pair_mags})"
            )
        return False

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
                else:
                    # Prefer richer/composite spectral strings from later rows.
                    row_spect = _normalize_spect(row.get("SpType", "") or "")
                    if row_spect and self._prefer_spect(row_spect, system.get("spect", "")):
                        system["spect"] = row_spect

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
        system: dict[str, Any] = {
            "wds": wds_id,
            "disc": row.get("Disc", "").strip() or None,
            "pos": [ra, dec],
            "pairs": [],
            "_score": -1e9,
        }
        # Prefer available catalogue cross-IDs when present (HIP/HD).
        hip = row.get("HIP", "") or row.get("Hip", "") or row.get("hip", "")
        hd = row.get("HD", "") or row.get("Hd", "") or row.get("hd", "")
        try:
            hip_i = int(hip) if hip else None
        except Exception:
            hip_i = None
        try:
            hd_i = int(hd) if hd else None
        except Exception:
            hd_i = None
        if hip_i is not None:
            system["hip"] = hip_i
        if hd_i is not None:
            system["hd"] = hd_i
        # Attempt to capture any provided spectral type for basic cross-checks
        spect = row.get("SpType", "") or row.get("Sp", "") or row.get("Spec", "")
        if spect:
            system["spect"] = _normalize_spect(spect)
        return system

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
    def _apparent_pair_separation_3d_au(
        s1: dict[str, Any], s2: dict[str, Any], sep_arcsec: float
    ) -> float | None:
        """3D projected separation (AU) between two stars at a given angular
        separation, or None when either lacks a parallax distance."""
        d1 = s1.get("dist")
        d2 = s2.get("dist")
        if d1 is None or d2 is None:
            return None
        theta_rad = sep_arcsec / 3600.0 * math.pi / 180.0
        proj_au = theta_rad * min(d1, d2) * _PC_TO_AU
        depth_au = abs(d1 - d2) * _PC_TO_AU
        return math.hypot(proj_au, depth_au)

    def _mark_pair_apparent_if_wide(
        self,
        s1: dict[str, Any],
        pair: dict[str, Any],
        candidates: list[dict[str, Any]],
        threshold_au: float,
    ) -> bool:
        """Check *pair* against the nearest matching candidate; mark it
        apparent (`vis`) and return True if its 3D separation exceeds
        *threshold_au*. Only the first candidate within the separation
        tolerance is ever considered, matching the original single-pass scan."""
        if "phys" in pair or "vis" in pair:
            return False
        sep_field = pair.get("sep")
        if sep_field is None:
            return False
        target_sep = sep_field[-1] if isinstance(sep_field, list) else sep_field
        for s2 in candidates:
            if s2 is s1:
                continue
            sep = _angular_sep_arcsec(s1["pos"], s2["pos"])
            if abs(sep - target_sep) > _APPARENT_PAIR_SEP_MATCH_TOL_ARCSEC:
                continue
            sep3d_au = self._apparent_pair_separation_3d_au(s1, s2, sep)
            if sep3d_au is None:
                break
            if sep3d_au > threshold_au:
                pair["vis"] = pair["comp"]
                return True
            break
        return False

    def classify_apparent_pairs(
        self,
        stars: list[dict[str, Any]],
        threshold_pc: float = 1.0,
    ) -> int:
        """Mark unclassified pairs as apparent using parallax distances.

        Returns count of pairs newly marked as apparent.
        """
        bins = self._build_spatial_bins([s for s in stars if s.get("dist") is not None])
        threshold_au = threshold_pc * _PC_TO_AU
        count = 0
        for s1 in stars:
            if not s1.get("dbl") or s1.get("dist") is None:
                continue
            candidates = self._get_bin_candidates(s1["pos"][0], s1["pos"][1], bins)
            for entry in s1["dbl"]:
                for pair in entry["pairs"]:
                    if self._mark_pair_apparent_if_wide(s1, pair, candidates, threshold_au):
                        count += 1
        return count

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
