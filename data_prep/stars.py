"""Star catalogue pipeline: HYG v4 CSV → data_prep/output/stars.json."""

import csv
import gzip
import json
import math
import re
from pathlib import Path
from typing import Any

from config import (
    ATHYG_FILENAME,
    ATHYG_FULL_FILENAMES,
    ATHYG_FULL_MAG_THRESHOLD,
    ATHYG_FULL_URLS,
    ATHYG_URL,
    EUROPE_MIN_DEC,
        EXTREME_STARS_NUM,
    MAX_STAR_MAGNITUDE,
    VARIABLE_THRESHOLD,
)
from double_stars import DoubleStarMatcher
from downloader import Downloader

# ---------------------------------------------------------------------------
# Spectral class → approximate CSS colour (B−V colour index approximation)
# ---------------------------------------------------------------------------

_SPECTRAL_COLOURS: dict[str, str] = {
    "O": "#92b5ff",  # blue-white
    "B": "#b2c5ff",  # blue-white
    "A": "#cad8ff",  # white (slight blue)
    "F": "#f8f7ff",  # white-yellow
    "G": "#fff4e8",  # yellow (Sun-like)
    "K": "#ffd2a1",  # orange
    "M": "#ff8f6b",  # orange-red
}
_DEFAULT_COLOUR: str = "#ffffff"

# Ordered colour palette used for the CSV encoding.  The index (0–7) stored in
# the CSV maps back to the hex string on the client via COLOR_PALETTE in db.js.
# Must stay in sync with COLOR_PALETTE in client/src/lib/db.js.
COLOR_PALETTE: list[str] = [
    "#92b5ff",  # 0 — O  blue-white
    "#b2c5ff",  # 1 — B  blue-white
    "#cad8ff",  # 2 — A  white (slight blue)
    "#f8f7ff",  # 3 — F  white-yellow
    "#fff4e8",  # 4 — G  yellow (Sun-like)
    "#ffd2a1",  # 5 — K  orange
    "#ff8f6b",  # 6 — M  orange-red
    "#ffffff",  # 7 — default / unknown
]
_COLOUR_TO_IDX: dict[str, int] = {c: i for i, c in enumerate(COLOR_PALETTE)}

# Stars with mag ≤ this limit go into Tier-1 (always in memory after startup).
# Stars with mag > this limit go into Tier-2 (fetched per zone on demand).
T1_MAG_LIMIT: float = 9.0

# Zone grid constants — must match ZONE_RA_CELLS / ZONE_DEC_CELLS in db.js.
_ZONE_RA_CELLS: int = 72   # 360 / 5
_ZONE_DEC_CELLS: int = 36  # 180 / 5
_ZONE_RA_BUCKET: float = 5.0
_ZONE_DEC_BUCKET: float = 5.0


def _compute_zone(ra_deg: float, dec_deg: float) -> int:
    """Compute the sky-zone integer matching computeZone() in db.js."""
    ra_cell = int(ra_deg / _ZONE_RA_BUCKET) % _ZONE_RA_CELLS
    dec_cell = min(_ZONE_DEC_CELLS - 1, int((dec_deg + 90) / _ZONE_DEC_BUCKET))
    return dec_cell * _ZONE_RA_CELLS + ra_cell


def spectral_colour(spect: str) -> str:
    """Return a CSS hex colour for a Harvard spectral class string.

    Examples::

        spectral_colour("A1V")   # → "#cad8ff"
        spectral_colour("M4III") # → "#ff8f6b"
        spectral_colour("")      # → "#ffffff"
    """
    if not spect:
        return _DEFAULT_COLOUR
    return _SPECTRAL_COLOURS.get(spect[0].upper(), _DEFAULT_COLOUR)


# ---------------------------------------------------------------------------
# Row-level helpers (pure functions for unit-testability)
# ---------------------------------------------------------------------------


def _load_notes(path: Path) -> dict[int, str]:
    """Return a HIP → note mapping loaded from a CSV sidecar file.

    Returns an empty dict when the file is absent (notes are optional).
    """
    if not path.exists():
        return {}
    notes: dict[int, str] = {}
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            hip = _int_or_none(row.get("hip", ""))
            note = row.get("note", "").strip()
            if hip and note:
                notes[hip] = note
    return notes


_BAYER_MAP: dict[str, str] = {
    "Alp": "α", "Bet": "β", "Gam": "γ", "Del": "δ", "Eps": "ε",
    "Zet": "ζ", "Eta": "η", "The": "θ", "Iot": "ι", "Kap": "κ",
    "Lam": "λ", "Mu":  "μ", "Nu":  "ν", "Xi":  "ξ", "Omi": "ο",
    "Pi":  "π", "Rho": "ρ", "Sig": "σ", "Tau": "τ", "Ups": "υ",
    "Phi": "φ", "Chi": "χ", "Psi": "ψ", "Ome": "ω",
}
_SUPERSCRIPTS: dict[int, int] = str.maketrans("123456789", "¹²³⁴⁵⁶⁷⁸⁹")


def _bayer_letter(raw: str) -> str | None:
    """Convert an AT-HYG bayer abbreviation to a Unicode Greek letter.

    ``"Alp"`` → ``"α"``, ``"Kap-1"`` → ``"κ¹"``. Returns ``None`` for empty
    or unrecognised input.
    """
    if not raw:
        return None
    parts = raw.split("-")
    letter = _BAYER_MAP.get(parts[0])
    if letter is None:
        return None
    if len(parts) == 2:
        letter += parts[1].translate(_SUPERSCRIPTS)
    return letter


# ---------------------------------------------------------------------------
# Physical property auto-notes from AT-HYG catalogue fields
# ---------------------------------------------------------------------------

_LUM_CLASS_LABELS: dict[str, str] = {
    "IA": "luminous supergiant",
    "IB": "supergiant",
    "I": "supergiant",
    "II": "bright giant",
    "III": "giant",
    "IV": "subgiant",
    "V": "main-sequence star",
}

_SPEC_TEMP_LABELS: dict[str, str] = {
    "O": "extremely hot blue",
    "B": "hot blue-white",
    "A": "white",
    "F": "yellow-white",
    "G": "yellow",
    "K": "orange",
    "M": "red",
    "W": "Wolf-Rayet",
    "C": "carbon",
    "S": "carbon-oxygen",
}

# Groups: (1) temperature-class letter  (2) MK luminosity class (optional)
# Examples: "B7III" → ("B", "III")  "M2 IA" → ("M", "IA")  "K5" → ("K", None)
_SPECT_PATTERN = re.compile(
    r"^([OBAFGKMWCS])"
    r"[0-9.]*"
    r"\s*"          # optional space between subtype and peculiarity/lum class
    r"[a-z]*"
    r"\s*"          # optional space before luminosity class (e.g. "M2 III")
    r"(I[ABab]|IV|I{1,3}|V)?",
)


def _lsun_str(l_sun: float) -> str:
    """Round solar luminosity to 1 significant figure and format with commas."""
    magnitude = 10 ** math.floor(math.log10(l_sun))
    return f"{int(round(l_sun / magnitude) * magnitude):,}"


def _parse_spec_class(spect: str) -> str | None:
    """Return a temperature label for a spectral type string.

    ``"B7III"`` → ``"hot blue-white"``, ``"M2IA"`` → ``"red"``.
    Returns ``None`` for empty or unparseable input.
    """
    if not spect:
        return None
    m = _SPECT_PATTERN.match(spect)
    return _SPEC_TEMP_LABELS.get(m.group(1).upper()) if m else None


def _parse_lum_class(spect: str) -> str | None:
    """Return a luminosity-class label for a spectral type string.

    ``"B7III"`` → ``"giant"``, ``"M2IA"`` → ``"luminous supergiant"``.
    Returns ``None`` when no standard MK luminosity class is present.
    """
    if not spect:
        return None
    m = _SPECT_PATTERN.match(spect)
    if not m or not m.group(2):
        return None
    return _LUM_CLASS_LABELS.get(m.group(2).upper())


def _auto_note(_spect: str, _absmag: float | None, _dist: float | None) -> str | None:
    """Auto-notes disabled: always return None.

    Curated notes in `notes_stars.csv` are preserved; automatic generation was
    intentionally removed per maintainer request.
    """
    return None


def _float_or_none(value: str) -> float | None:
    try:
        return float(value) if value else None
    except ValueError:
        return None


def _int_or_none(value: str) -> int | None:
    try:
        n = int(value) if value else None
        return n if n else None  # treat 0 as absent (no HIP/HD/SAO 0)
    except ValueError:
        return None


def _is_variable(
    var_min: float | None,
    var_max: float | None,
    threshold: float = VARIABLE_THRESHOLD,
) -> bool:
    """Return True when the magnitude range meets or exceeds *threshold*."""
    if var_min is None or var_max is None:
        return False
    return (var_max - var_min) >= threshold


def _build_star(
    row: dict[str, str],
    max_mag: float = MAX_STAR_MAGNITUDE,
    min_dec: float = EUROPE_MIN_DEC,
    var_range: tuple[float, float] | None = None,
    var_threshold: float = VARIABLE_THRESHOLD,
) -> dict[str, Any] | None:
    """Convert a raw CSV row to a star dict; return None to skip.

    Filtering rules:
    - Magnitude must be ≤ max_mag.
    - Declination must be ≥ min_dec.
    - Rows with unparseable ra, magnitude or declination are dropped.
    - Rows with dist=0 are dropped (Sun placeholder in AT-HYG).
    - Rows with missing distance are retained; the dist field is omitted from output.
    """
    mag = _float_or_none(row.get("mag", ""))
    ra = _float_or_none(row.get("ra", ""))
    dec = _float_or_none(row.get("dec", ""))
    if mag is None or ra is None or dec is None:
        return None
    dist = _float_or_none(row.get("dist", ""))
    if dist == 0.0:
        return None  # excludes the Sun (dist=0 placeholder in AT-HYG)
    if mag > max_mag or dec < min_dec:
        return None

    spect = row.get("spect", "")
    mag_value: float | list[float] = (
        [var_range[0], var_range[1]]
        if var_range is not None
        and _is_variable(var_range[0], var_range[1], var_threshold)
        else mag
    )
    star: dict[str, Any] = {
        "pos": [ra, dec],
        "mag": mag_value,
        "clr": spectral_colour(spect),
    }
    for key, value in (
        ("hip", _int_or_none(row.get("hip", ""))),
        ("hd", _int_or_none(row.get("hd", ""))),
        ("bay", _bayer_letter(row.get("bayer", ""))),
        ("flam", _int_or_none(row.get("flam", ""))),
        ("name", row.get("proper", "") or None),
        ("spect", spect or None),
        ("dist", dist),
        ("const", row.get("con", "") or None),
        ("pm_ra", _float_or_none(row.get("pm_ra", ""))),
        ("pm_dec", _float_or_none(row.get("pm_dec", ""))),
    ):
        if value is not None:
            star[key] = value
    return star


# ---------------------------------------------------------------------------
# Pipeline class
# ---------------------------------------------------------------------------


class StarPipeline:
    """Downloads HYG v4, filters stars, and writes stars.json."""

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        sources_dir: Path,
        output_dir: Path,
        cache_dir: Path | None = None,
        max_mag: float = MAX_STAR_MAGNITUDE,
        var_threshold: float = VARIABLE_THRESHOLD,
        min_double_star_sep: float = 2.0,
        debug: bool = False,
    ) -> None:
        self._sources_dir = sources_dir
        self._output_dir = output_dir
        self._max_mag = max_mag
        self._var_threshold = var_threshold
        self._min_double_star_sep = min_double_star_sep
        # Use a dedicated cache directory for network downloads while keeping
        # sidecar sources in `sources/` tracked in VCS.
        cache = cache_dir or sources_dir
        self._downloader = Downloader(cache, debug=debug)
        self._double_matcher = DoubleStarMatcher(sources_dir, cache_dir=cache, debug=debug)
        self._debug = debug

    def run(
        self,
        var_index: dict[int, tuple[float, float]] | None = None,
        attach_double: bool = False,
        show_summary: bool = True,
        extreme_stars_num: int | None = None,
    ) -> Path:
        """Execute the pipeline and return the path to stars.json.

        *var_index* is an optional HIP → (min_mag, max_mag) mapping supplied
        by :class:`~variable_stars.VariableStarPipeline`. When absent, no
        variable-star encoding is applied.

        By default this method does not attach double-star metadata; set
        *attach_double* to True to perform double-star matching inline.
        """
        if self._max_mag > ATHYG_FULL_MAG_THRESHOLD:
            csv_paths = [
                self._downloader.fetch(url, name)
                for url, name in zip(ATHYG_FULL_URLS, ATHYG_FULL_FILENAMES, strict=True)
            ]
        else:
            csv_paths = [self._downloader.fetch(ATHYG_URL, ATHYG_FILENAME)]
        notes_path = self._sources_dir / "notes_stars.csv"
        notes = _load_notes(notes_path)
        stars, n_curated, _ = self._process(csv_paths, var_index or {}, notes)
        # Compute luminosities and annotate the most luminous stars. Recompute
        # the post-annotation auto-note count so only the top N are reported
        # as auto-generated notes.

        top_n = extreme_stars_num if extreme_stars_num is not None else EXTREME_STARS_NUM
        self._safe_annotate(self._annotate_luminosity, stars, top_n)
        self._safe_annotate(self._annotate_brightness, stars, top_n)
        self._safe_annotate(self._annotate_pm, stars, top_n)
        self._safe_annotate(self._annotate_most_variable, stars, var_index or {}, top_n)
        self._safe_annotate(self._annotate_nearest, stars, top_n)
        self._safe_annotate(self._annotate_hottest, stars, top_n)
        self._safe_annotate(self._annotate_space_velocity, stars, top_n)
        # Compute the number of unique stars that received auto-generated
        # notes (marked by the helper flag set above).
        summary_ids: set[int] = {id(s) for s in stars if s.get("_auto_note")}
        n_auto = len(summary_ids)
        if attach_double:
            n_dbl_stars, n_dbl_pairs = self._double_matcher.attach(
                stars,
                max_mag=self._max_mag,
                min_sep=self._min_double_star_sep,
            )
        else:
            n_dbl_stars = 0
            n_dbl_pairs = 0
        self._write_csv(stars)
        return self._write(
            stars,
            n_curated,
            n_auto,
            n_dbl_stars,
            n_dbl_pairs,
            show_variables=(bool(var_index) and (show_summary or self._debug)),
            show_double=(attach_double and (show_summary or self._debug)),
            show_summary=show_summary,
        )

    def _safe_annotate(self, fn: Any, *args: Any) -> None:
        try:
            fn(*args)
        except Exception:  # pylint: disable=broad-except
            if self._debug:
                raise

    def _annotate_luminosity(self, stars: list[dict[str, Any]], top_n: int) -> int:
        """Compute luminosity (L/L_sun) for stars with `mag` (float) and `dist` (pc).

        Adds temporary `_lsun` (float) and `_lsun_phrase` (str) and appends the
        phrase to `note` so that `_cap_luminosity_notes()` can trim it for all
        but the top *top_n* entries. After capping, adds a persistent note
        "Among the X stars with highest luminosity" to those top entries.
        """
        with_lsun = []
        for star in stars:
            if self._assign_lsun_to_star(star):
                with_lsun.append(star)
        if not with_lsun:
            return 0
        # Determine top N by luminosity (handle top_n > available)
        actual_top = max(0, min(top_n, len(with_lsun)))
        top_list = sorted(with_lsun, key=lambda s: s["_lsun"], reverse=True)[:actual_top]
        # Cap/remove luminosity phrases and temp fields per existing behaviour
        self._cap_luminosity_notes(stars, top_n=actual_top)
        # Add persistent summary into `smr` for the top items.
        for idx, star in enumerate(top_list, start=1):
            if idx == 1:
                summary = "The star with the highest luminosity"
            elif idx == 2:
                summary = "A star with the 2nd highest luminosity"
            elif idx == 3:
                summary = "A star with the 3rd highest luminosity"
            else:
                summary = f"Among the {actual_top} stars with highest luminosity"
            if "smr" in star and star["smr"]:
                star["smr"] = f"{star['smr']}; {summary}"
            else:
                star["smr"] = summary
            star["_auto_note"] = True
        return actual_top

    def _annotate_brightness(self, stars: list[dict[str, Any]], top_n: int) -> int:
        """Mark the top *top_n* stars by apparent brightness (lowest `mag`).

        Appends a persistent summary note "Among the X brightest stars" to
        each of the selected stars and returns the actual number marked.
        """
        with_mag = [s for s in stars if isinstance(s.get("mag"), float)]
        if not with_mag:
            return 0
        actual_top = max(0, min(top_n, len(with_mag)))
        # sort by apparent magnitude (smaller = brighter)
        top_stars = sorted(with_mag, key=lambda s: s["mag"])[:actual_top]
        for idx, s in enumerate(top_stars, start=1):
            if idx == 1:
                summary = "The brightest star in the sky"
            elif idx == 2:
                summary = "The 2nd brightest star in the sky"
            elif idx == 3:
                summary = "The 3rd brightest star in the sky"
            else:
                summary = f"Among the {actual_top} brightest stars"
            if "smr" in s and s["smr"]:
                s["smr"] = f"{s['smr']}; {summary}"
            else:
                s["smr"] = summary
            s["_auto_note"] = True
        return actual_top

    def _annotate_pm(self, stars: list[dict[str, Any]], top_n: int) -> int:
        """Mark the top *top_n* stars by proper motion (pm_ra, pm_dec).

        Proper motion magnitude is computed as sqrt(pm_ra^2 + pm_dec^2)
        where the fields are expected in mas/yr. Top-ranked stars receive
        special phrasing for ranks 1..3; others receive a summary note.
        """
        with_pm = []
        for s in stars:
            pm_ra = s.get("pm_ra")
            pm_dec = s.get("pm_dec")
            if isinstance(pm_ra, (int, float)) and isinstance(pm_dec, (int, float)):
                s["_pm"] = float(math.hypot(pm_ra, pm_dec))
                with_pm.append(s)
        if not with_pm:
            return 0
        actual_top = max(0, min(top_n, len(with_pm)))
        top_list = sorted(with_pm, key=lambda s: s["_pm"], reverse=True)[:actual_top]
        def _fmt_arcsec_per_year(pm_masyr: float) -> str:
            # mas/yr -> arcsec/yr: arcsec = pm_masyr / 1000
            arcsec = pm_masyr / 1000.0
            # Format with 2 decimal places for readability
            return f"{arcsec:.2f}\"/yr"

        for idx, s in enumerate(top_list, start=1):
            if idx == 1:
                summary = "The star with the highest proper motion"
            elif idx == 2:
                summary = "The star with the 2nd highest proper motion"
            elif idx == 3:
                summary = "The star with the 3rd highest proper motion"
            else:
                summary = f"Among the {actual_top} stars with highest proper motion"
            # append a human-readable proper-motion rate (arcsec per year)
            pm_val = s.get("_pm")
            if isinstance(pm_val, (int, float)):
                pm_str = _fmt_arcsec_per_year(pm_val)
                summary = f"{summary} - {pm_str}"
            if "smr" in s and s["smr"]:
                s["smr"] = f"{s['smr']}; {summary}"
            else:
                s["smr"] = summary
            s["_auto_note"] = True
        return actual_top

    @staticmethod
    def _collect_variable_amplitudes(
        stars: list[dict[str, Any]],
        var_index: dict[int, tuple[float, float]],
    ) -> list[tuple[dict[str, Any], float]]:
        result: list[tuple[dict[str, Any], float]] = []
        for s in stars:
            hip = s.get("hip")
            if hip and hip in var_index:
                rng = var_index[hip]
                if rng and isinstance(rng[0], (int, float)) and isinstance(rng[1], (int, float)):
                    amp = rng[1] - rng[0]
                    if amp > 0:
                        result.append((s, amp))
        return result

    def _annotate_most_variable(
        self,
        stars: list[dict[str, Any]],
        var_index: dict[int, tuple[float, float]] | None,
        top_n: int,
    ) -> int:
        """Mark the top *top_n* stars by variability amplitude from *var_index*.

        *var_index* is a HIP -> (min_mag, max_mag) mapping.
        """
        if not var_index:
            return 0
        var_list = self._collect_variable_amplitudes(stars, var_index)
        if not var_list:
            return 0
        var_list.sort(key=lambda x: x[1], reverse=True)
        actual_top = max(0, min(top_n, len(var_list)))
        for idx, (s, amp) in enumerate(var_list[:actual_top], start=1):
            if idx == 1:
                summary = f"The most variable star (amplitude {amp:.2f} mag)"
            elif idx == 2:
                summary = f"The 2nd most variable star (amplitude {amp:.2f} mag)"
            elif idx == 3:
                summary = f"The 3rd most variable star (amplitude {amp:.2f} mag)"
            else:
                summary = f"Among the {actual_top} most variable stars (amplitude {amp:.2f} mag)"
            if "smr" in s and s["smr"]:
                s["smr"] = f"{s['smr']}; {summary}"
            else:
                s["smr"] = summary
            s["_auto_note"] = True
        return actual_top

    def _annotate_nearest(self, stars: list[dict[str, Any]], top_n: int) -> int:
        """Mark the top *top_n* nearest stars (showing distance in ly)."""
        with_dist = [
            s
            for s in stars
            if isinstance(s.get("dist"), (int, float)) and s.get("dist") > 0
        ]
        if not with_dist:
            return 0
        with_dist.sort(key=lambda s: s["dist"])  # ascending pc
        actual_top = max(0, min(top_n, len(with_dist)))
        for idx, s in enumerate(with_dist[:actual_top], start=1):
            ly = s["dist"] * 3.26156
            if idx == 1:
                summary = f"The nearest star — {ly:.2f} ly"
            elif idx == 2:
                summary = f"The 2nd nearest star — {ly:.2f} ly"
            elif idx == 3:
                summary = f"The 3rd nearest star — {ly:.2f} ly"
            else:
                summary = f"Among the {actual_top} nearest stars — {ly:.2f} ly"
            if "smr" in s and s["smr"]:
                s["smr"] = f"{s['smr']}; {summary}"
            else:
                s["smr"] = summary
            s["_auto_note"] = True
        return actual_top

    def _annotate_hottest(self, stars: list[dict[str, Any]], top_n: int) -> int:
        """Rank by Harvard spectral class (O hottest → M coolest)."""
        order = {"O": 0, "B": 1, "A": 2, "F": 3, "G": 4, "K": 5, "M": 6, "W": 7, "C": 8, "S": 9}
        parsed: list[tuple[dict[str, Any], int, float]] = []
        for s in stars:
            spect = s.get("spect") or ""
            if not spect:
                continue
            m = re.match(r"^([OBAFGKMWCS])([0-9.]*)", spect.strip(), re.I)
            if not m:
                continue
            letter = m.group(1).upper()
            subtype = float(m.group(2)) if m.group(2) else 5.0
            rank_key = order.get(letter, 99)
            parsed.append((s, rank_key, subtype))
        if not parsed:
            return 0
        parsed.sort(key=lambda x: (x[1], x[2]))
        actual_top = max(0, min(top_n, len(parsed)))
        for idx, (s, _, _) in enumerate(parsed[:actual_top], start=1):
            if idx == 1:
                summary = "The hottest star"
            elif idx == 2:
                summary = "The 2nd hottest star"
            elif idx == 3:
                summary = "The 3rd hottest star"
            else:
                summary = f"Among the {actual_top} hottest stars"
            if "smr" in s and s["smr"]:
                s["smr"] = f"{s['smr']}; {summary}"
            else:
                s["smr"] = summary
            s["_auto_note"] = True
        return actual_top

    def _assign_lsun_to_star(self, star: dict[str, Any]) -> bool:
        """Compute and attach luminosity fields for *star*.

        Returns True if luminosity was computed and attached, False otherwise.
        """
        m_sun = 4.83
        mag = star.get("mag")
        dist = star.get("dist")
        if not (isinstance(mag, float) and isinstance(dist, (int, float)) and dist and dist > 0):
            return False
        try:
            abs_mag = mag - 5 * math.log10(dist / 10)
            lsun = 10 ** ((m_sun - abs_mag) / 2.5)
        except (ValueError, OverflowError):
            return False
        star["_lsun"] = float(lsun)
        phrase = f"~{_lsun_str(lsun)}\u00d7 the Sun's luminosity"
        star["_lsun_phrase"] = phrase
        # Auto-generated phrases go into the `smr` (summary) field. Always
        # attach the luminosity phrase to `smr` so curated `note` remains
        # untouched while still recording autogenerated summaries.
        if "smr" in star and star["smr"]:
            star["smr"] = f"{star['smr']}; {phrase}"
        else:
            star["smr"] = phrase
        return True

    def _process_row(
        self,
        row: dict[str, str],
        var_index: dict[int, tuple[float, float]],
        notes: dict[int, str],
    ) -> tuple[dict[str, Any] | None, int, int]:
        """Process one CSV row; return (star_or_None, n_curated_delta, n_auto_delta)."""
        hip = _int_or_none(row.get("hip", ""))
        var_range = var_index.get(hip) if hip else None
        star = _build_star(
            row,
            max_mag=self._max_mag,
            var_range=var_range,
            var_threshold=self._var_threshold,
        )
        if star is None:
            return None, 0, 0
        if hip and hip in notes:
            # Attach curated note into `note` (preserve curated text).
            star["note"] = notes[hip]
            star["_curated_note"] = True
            return star, 1, 0
        # Auto-generated physical notes have been disabled. Preserve curated
        # notes only; count no auto notes.
        return star, 0, 0

    def _process_file(
        self,
        csv_path: Path,
        fieldnames: list[str] | None,
        var_index: dict[int, tuple[float, float]],
        notes: dict[int, str],
    ) -> tuple[list[dict[str, Any]], int, int, list[str]]:
        """Read one catalogue file; return (stars, n_curated, n_auto, fieldnames)."""
        stars: list[dict[str, Any]] = []
        n_curated = 0
        n_auto = 0
        opener = gzip.open if csv_path.suffix == ".gz" else open
        with opener(csv_path, "rt", encoding="utf-8") as fh:
            reader = csv.DictReader(fh, fieldnames=fieldnames)
            for row in reader:
                star, dc, da = self._process_row(row, var_index, notes)
                if star is not None:
                    stars.append(star)
                    n_curated += dc
                    n_auto += da
        return stars, n_curated, n_auto, list(reader.fieldnames or [])

    def _process(
        self,
        csv_paths: list[Path],
        var_index: dict[int, tuple[float, float]],
        notes: dict[int, str],
    ) -> tuple[list[dict[str, Any]], int, int]:
        """Parse one or more CSV files and return (stars, n_curated, n_auto).

        When multiple files are given (full AT-HYG catalogue split into parts),
        only the first file contains a header row; subsequent parts share the
        same schema and must be read with the header extracted from the first.
        """
        stars: list[dict[str, Any]] = []
        n_curated = 0
        n_auto = 0
        shared_fieldnames: list[str] | None = None
        for idx, csv_path in enumerate(csv_paths):
            batch, dc, da, fnames = self._process_file(
                csv_path,
                None if idx == 0 else shared_fieldnames,
                var_index,
                notes,
            )
            stars.extend(batch)
            n_curated += dc
            n_auto += da
            if idx == 0:
                shared_fieldnames = fnames
        # Auto-luminosity notes and auto-generated notes are disabled.
        # Curated notes from `notes_stars.csv` are preserved and counted.
        return stars, n_curated, n_auto

    @staticmethod
    def _cap_luminosity_notes(
        stars: list[dict[str, Any]], top_n: int = 5
    ) -> None:
        """Keep the luminosity phrase only for the *top_n* most luminous stars."""
        tagged = sorted(
            [s for s in stars if "_lsun" in s],
            key=lambda s: s["_lsun"],
            reverse=True,
        )
        for s in tagged[top_n:]:
            phrase = s.pop("_lsun_phrase", None)
            # Remove the phrase from the note and summary fields in all
            # common positions so only the top-N keep the luminosity claim.
            if phrase:
                smr = s.get("smr")
                if smr:
                    new = smr.replace(f"; {phrase}", "").replace(f"{phrase}; ", "")
                    new = new.replace(phrase, "")
                    new = re.sub(r"\s*;\s*", "; ", new).strip()
                    new = new.strip("; ")
                    if new:
                        s["smr"] = new
                    else:
                        s.pop("smr", None)

                note = s.get("note")
                if note:
                    newn = note.replace(f"; {phrase}", "").replace(f"{phrase}; ", "")
                    newn = newn.replace(phrase, "")
                    newn = re.sub(r"\s*;\s*", "; ", newn).strip()
                    newn = newn.strip("; ")
                    if newn:
                        s["note"] = newn
                    else:
                        s.pop("note", None)
            s.pop("_lsun", None)
        for s in tagged[:top_n]:
            s.pop("_lsun", None)
            s.pop("_lsun_phrase", None)

    def _write_csv(
        self,
        stars: list[dict[str, Any]],
    ) -> tuple[Path, Path]:
        """Write Tier-1 and Tier-2 star CSVs alongside the JSON output.

        Returns (path_t1, path_t2).
        """
        self._output_dir.mkdir(parents=True, exist_ok=True)
        mag_tag = f"m{self._max_mag:g}"
        path_t1 = self._output_dir / f"stars_t1.{mag_tag}.csv"
        path_t2 = self._output_dir / f"stars_t2.{mag_tag}.csv"

        def _mag_sort(s: dict[str, Any]) -> float:
            m = s["mag"]
            return m[0] if isinstance(m, list) else m

        def _encode_mag(m: Any) -> str:
            if isinstance(m, list):
                return f"{m[0]:.2f}:{m[1]:.2f}"
            return f"{m:.2f}"

        def _col_idx(s: dict[str, Any]) -> int:
            return _COLOUR_TO_IDX.get(s.get("clr", ""), len(COLOR_PALETTE) - 1)

        t1_header = "ra,de,mg,cl,hp,hd,sp,ds,pr,pd,fl,by,db,nm,nt,sm"
        t1_fixed_cols = 10   # columns before the optional trailing group
        t2_header = "z,ra,de,mg,cl,hp,hd,sp,ds,pr,pd"

        tier1 = sorted([s for s in stars if _mag_sort(s) <= T1_MAG_LIMIT], key=_mag_sort)
        tier2 = sorted(
            [s for s in stars if _mag_sort(s) > T1_MAG_LIMIT],
            key=lambda s: (_compute_zone(s["pos"][0] * 15, s["pos"][1]), _mag_sort(s)),
        )

        with path_t1.open("w", encoding="utf-8", newline="") as fh:
            fh.write(t1_header + "\n")
            for s in tier1:
                ra_deg = s["pos"][0] * 15
                dec = s["pos"][1]
                row: list[str] = [
                    f"{ra_deg:.4f}",
                    f"{dec:.4f}",
                    _encode_mag(s["mag"]),
                    str(_col_idx(s)),
                    str(s["hip"]) if s.get("hip") else "",
                    str(s["hd"]) if s.get("hd") else "",
                    (s.get("spect") or "")[:2],
                    f"{s['dist']:.1f}" if s.get("dist") is not None else "",
                    f"{s['pm_ra']:.2f}" if s.get("pm_ra") is not None else "",
                    f"{s['pm_dec']:.2f}" if s.get("pm_dec") is not None else "",
                    # optional trailing
                    str(s["flam"]) if s.get("flam") else "",
                    s.get("bay") or "",
                    "1" if s.get("dbl") else "",
                    s.get("name") or "",
                    s.get("note") or "",
                    s.get("smr") or "",
                ]
                # Strip trailing empty optional columns to save space.
                while len(row) > t1_fixed_cols and row[-1] == "":
                    row.pop()
                fh.write(",".join(row) + "\n")

        with path_t2.open("w", encoding="utf-8", newline="") as fh:
            fh.write(t2_header + "\n")
            for s in tier2:
                ra_deg = s["pos"][0] * 15
                dec = s["pos"][1]
                zone = _compute_zone(ra_deg, dec)
                row = [
                    str(zone),
                    f"{ra_deg:.4f}",
                    f"{dec:.4f}",
                    _encode_mag(s["mag"]),
                    str(_col_idx(s)),
                    str(s["hip"]) if s.get("hip") else "",
                    str(s["hd"]) if s.get("hd") else "",
                    (s.get("spect") or "")[:2],
                    f"{s['dist']:.1f}" if s.get("dist") is not None else "",
                    f"{s['pm_ra']:.2f}" if s.get("pm_ra") is not None else "",
                    f"{s['pm_dec']:.2f}" if s.get("pm_dec") is not None else "",
                ]
                fh.write(",".join(row) + "\n")

        print(f"Stars CSV T1    : {len(tier1):,} rows → {path_t1}")
        print(f"Stars CSV T2    : {len(tier2):,} rows → {path_t2}")
        return path_t1, path_t2

    # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    def _write(
        self,
        stars: list[dict[str, Any]],
        n_curated: int,
        n_auto: int,
        n_dbl_stars: int,
        n_dbl_pairs: int,
        show_variables: bool = False,
        show_double: bool = False,
        show_summary: bool = True,
    ) -> Path:
        """Group stars by constellation, write JSON, print stats, return path."""
        self._output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"stars.m{self._max_mag:g}.json"
        out = self._output_dir / filename
        grouped: dict[str, list[dict[str, Any]]] = {}
        for star in stars:
            key = star.pop("const", None) or "NO_CONST"
            # Rewrite autogenerated summaries into a concise form that
            # indicates these are limited to the survey coverage
            # (Europe-visible). e.g. "The 3rd nearest star — 8.60 ly" ->
            # "The 3rd nearest star visible from Europe — 8.60 ly".
            if star.get("_auto_note") and star.get("smr"):
                raw = star.get("smr", "")
                # split multiple summary clauses joined with ";"
                parts = [p.strip() for p in raw.split(";") if p.strip()]
                new_parts: list[str] = []
                for p in parts:
                    # remove any previous long-form suffix if present
                    p = p.replace("(Northern-sky survey — southern stars excluded)", "").strip()
                    # prefer the em-dash separator " — ", else hyphen " - "
                    if " — " in p:
                        lead, sep, tail = p.partition(" — ")
                    elif " - " in p:
                        lead, sep, tail = p.partition(" - ")
                    else:
                        lead, sep, tail = p, "", ""
                    # Avoid duplicating similar suffixes; prefer the
                    # concise phrase "visible from Europe".
                    if "visible from Europe" not in lead and "Europe-visible" not in lead:
                        lead = f"{lead} visible from Europe"
                    new = f"{lead}{sep}{tail}" if sep else lead
                    new_parts.append(new)
                star["smr"] = "; ".join(new_parts)
            # Remove internal helper flags before writing output
            for helper in ["_lsun", "_lsun_phrase", "_curated_note", "_auto_note", "_pm"]:
                star.pop(helper, None)
            grouped.setdefault(key, []).append(star)
        with out.open("w", encoding="utf-8") as fh:
            json.dump(grouped, fh, ensure_ascii=False)
        if show_summary:
            size_mb = out.stat().st_size / 1_048_576
            n_variable = sum(1 for s in stars if isinstance(s.get("mag"), list))
            note_parts = ([f"{n_curated} curated"] if n_curated else []) + (
                [f"{n_auto} auto-generated"] if n_auto else []
            )
            notes_summary = " + ".join(note_parts) if note_parts else "none"
            print(
                f"Stars included : {len(stars):,} across {len(grouped):,} "
                "constellations"
            )
            if show_variables:
                print(
                    f"Variable stars : {n_variable} encoded with amplitude \u2265 "
                    f"{self._var_threshold}"
                )
            if show_double:
                print(
                    f"Double stars   : {n_dbl_stars} stars with {n_dbl_pairs} pairs "
                    f"(sep >= {self._min_double_star_sep} arcsec)"
                )
            print(f"Star notes     : {notes_summary}")
            print(f"Output         : {out} ({size_mb:.2f} MB)")
        return out
    # pylint: enable=too-many-arguments,too-many-positional-arguments,too-many-locals

    @staticmethod
    def _compute_space_velocity(s: dict[str, Any]) -> float | None:
        pm_ra = s.get("pm_ra")
        pm_dec = s.get("pm_dec")
        dist = s.get("dist")
        if not (
            isinstance(pm_ra, (int, float))
            and isinstance(pm_dec, (int, float))
            and isinstance(dist, (int, float))
            and dist > 0
        ):
            return None
        mu_masyr = math.hypot(pm_ra, pm_dec)
        mu_arcsec = mu_masyr / 1000.0
        vt = 4.74047 * mu_arcsec * dist
        rv = s.get("rv")
        if isinstance(rv, (int, float)):
            return math.hypot(vt, rv)
        return vt

    def _annotate_space_velocity(
        self, stars: list[dict[str, Any]], top_n: int
    ) -> int:
        """Annotate stars with highest total space velocity (km/s).

        Uses `pm_ra`, `pm_dec` (mas/yr), `dist` (pc) and optional `rv` (km/s).
        Ranks by total velocity sqrt(vt^2 + rv^2) when RV present, else by vt.
        Notes only include the total km/s rounded to 1 decimal place.
        """
        vals: list[tuple[dict[str, Any], float]] = []
        for s in stars:
            vtot = self._compute_space_velocity(s)
            if vtot is not None:
                vals.append((s, vtot))
        if not vals:
            return 0
        vals.sort(key=lambda x: x[1], reverse=True)
        actual_top = max(0, min(top_n, len(vals)))
        for idx, (s, vtot) in enumerate(vals[:actual_top], start=1):
            if idx == 1:
                summary = f"The star with the highest total space velocity — {vtot:.1f} km/s"
            elif idx == 2:
                summary = f"The star with the 2nd highest total space velocity — {vtot:.1f} km/s"
            elif idx == 3:
                summary = f"The star with the 3rd highest total space velocity — {vtot:.1f} km/s"
            else:
                summary = (
                    f"Among the {actual_top} stars with highest total space velocity — "
                    f"{vtot:.1f} km/s"
                )
            if "smr" in s and s["smr"]:
                s["smr"] = f"{s['smr']}; {summary}"
            else:
                s["smr"] = summary
            s["_auto_note"] = True
        return actual_top
