"""Comet pipeline: MPC comet orbital elements -> comet records for solar_system.json.

Data source: https://www.minorplanetcenter.net/iau/MPCORB/CometEls.txt

Fixed-width column layout (0-indexed). MPC's own published documentation is
inconsistent about a couple of these ranges, so this was verified directly
against a live sample of the file (including 1P/Halley, 2P/Encke, and two
unnumbered comets):

    [0:4]     Periodic number (blank if not a numbered periodic comet)
    [4:5]     Orbit type (C/P/D/A/I)
    [5:13]    Provisional designation, packed form (blank if numbered)
    [13:18]   Year of perihelion passage
    [18:21]   Month of perihelion passage
    [21:29]   Day of perihelion passage (TT, fractional)
    [29:39]   Perihelion distance q (AU)
    [39:49]   Eccentricity e
    [49:59]   Argument of perihelion (degrees, J2000)
    [59:69]   Longitude of ascending node (degrees, J2000)
    [69:79]   Inclination (degrees, J2000)
    [79:89]   Epoch of elements (YYYYMMDD, plain — unlike MPCORB's packed
              asteroid epoch)
    [89:95]   Absolute magnitude parameter (H / M1)
    [95:100]  Slope parameter (n)
    [100:158] Name
    [158:]    Reference
"""

import math
from pathlib import Path
from typing import Any

from config import COMET_ELEMENTS_FILENAME, COMET_ELEMENTS_URL, COMET_MAX_MAGNITUDE
from downloader import Downloader

_MIN_LINE_LEN = 158


def _to_julian_date(year: int, month: int, day_int: int, day_frac: float) -> float:
    """Convert a calendar date (TT) to a Julian Date.

    Uses the standard Fliegel-Van Flandern Julian Day Number algorithm (the
    same one used client-side in SkyCanvas.svelte's `_mpcEpochToJD`), adjusted
    from the noon-based JDN to a JD that accounts for the time-of-day fraction.
    """
    a = (14 - month) // 12
    y = year + 4800 - a
    m = month + 12 * a - 3
    jdn = (
        day_int
        + (153 * m + 2) // 5
        + 365 * y
        + y // 4
        - y // 100
        + y // 400
        - 32045
    )
    return jdn - 0.5 + day_frac


def _parse_perihelion_jd(year_s: str, month_s: str, day_s: str) -> float | None:
    try:
        year = int(year_s)
        month = int(month_s)
        day_frac = float(day_s)
    except ValueError:
        return None
    day_int = math.floor(day_frac)
    return _to_julian_date(year, month, day_int, day_frac - day_int)


def _estimate_peak_magnitude(h: float, slope_n: float, q: float) -> float:
    """Rough best-case peak apparent magnitude: evaluated at perihelion (r=q)
    with a favorable near-minimum Earth distance, using the comet magnitude
    law `V = H + 5*log10(delta) + 2.5*n*log10(r)`.

    Comet brightness predictions are inherently unreliable (real apparitions
    routinely over- or under-perform this formula) — this is a coarse
    inclusion filter, not a promise of visibility or accurate magnitude.
    """
    delta = max(0.1, abs(q - 1.0))
    r = max(q, 0.05)
    return h + 5.0 * math.log10(delta) + 2.5 * slope_n * math.log10(r)


def _parse_comet_line(line: str) -> dict[str, Any] | None:
    """Parse one line of MPC's CometEls.txt fixed-width format.

    Returns None if the line is too short or required fields are missing or
    unparseable.
    """
    if len(line) < _MIN_LINE_LEN:
        return None

    try:
        periodic_num = line[0:4].strip()
        orbit_type = line[4:5].strip()
        year_s = line[13:18].strip()
        month_s = line[18:21].strip()
        day_s = line[21:29].strip()
        q_s = line[29:39].strip()
        e_s = line[39:49].strip()
        arg_peri_s = line[49:59].strip()
        asc_node_s = line[59:69].strip()
        incl_s = line[69:79].strip()
        h_s = line[89:95].strip()
        slope_s = line[95:100].strip()
        name = line[100:158].strip()

        if not (year_s and month_s and day_s and q_s and e_s and h_s and slope_s and name):
            return None

        tp_jd = _parse_perihelion_jd(year_s, month_s, day_s)
        if tp_jd is None:
            return None

        return {
            "designation": periodic_num + orbit_type if periodic_num else name,
            "name": name,
            "q": float(q_s),
            "e": float(e_s),
            "argOfPeriDeg": float(arg_peri_s),
            "ascNodeDeg": float(asc_node_s),
            "inclDeg": float(incl_s),
            "tpJd": tp_jd,
            "H": float(h_s),
            "slopeN": float(slope_s),
        }
    except (ValueError, IndexError):
        return None


class CometPipeline:
    """Downloads and filters MPC comet orbital elements."""

    def __init__(self, cache_dir: Path, debug: bool = False) -> None:
        self._downloader = Downloader(cache_dir, debug=debug)

    def fetch_comets(self, max_mag: float | None = None) -> list[dict[str, Any]]:
        """Download CometEls.txt and return comets estimated to reach `max_mag`.

        Args:
            max_mag: Maximum estimated peak apparent magnitude. Defaults to
                COMET_MAX_MAGNITUDE.

        Returns:
            List of comet orbital-element records, brightest first.
        """
        cutoff = COMET_MAX_MAGNITUDE if max_mag is None else max_mag
        source = self._downloader.fetch(COMET_ELEMENTS_URL, COMET_ELEMENTS_FILENAME)

        comets: list[dict[str, Any]] = []
        with source.open("r", encoding="utf-8", errors="ignore") as f:
            for raw_line in f:
                line = raw_line.rstrip("\n")
                if not line.strip():
                    continue
                record = _parse_comet_line(line)
                if record is None:
                    continue
                peak_mag = _estimate_peak_magnitude(record["H"], record["slopeN"], record["q"])
                if peak_mag <= cutoff:
                    record["estPeakMag"] = round(peak_mag, 1)
                    comets.append(record)

        comets.sort(key=lambda c: c["estPeakMag"])
        return comets
