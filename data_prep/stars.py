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


def _auto_note(spect: str, absmag: float | None, dist: float | None) -> str | None:
    """Generate a concise physical description from AT-HYG catalogue fields.

    Only emits a note for extremal cases: supergiants/bright giants, O-type or
    rare-type stars (WR/C/S), and very nearby stars (within 33 light-years).
    Tier-2 curated notes always take precedence over this auto-generated text.
    """
    temp_label = _parse_spec_class(spect)
    lum_label = _parse_lum_class(spect)

    if not temp_label and not lum_label:
        return None

    supergiant_labels = {"luminous supergiant", "supergiant", "bright giant"}
    rare_temp_labels = {"extremely hot blue", "Wolf-Rayet", "carbon", "carbon-oxygen"}
    is_supergiant = lum_label in supergiant_labels
    is_rare_type = temp_label in rare_temp_labels
    is_nearby = dist is not None and dist * 3.2616 < 33

    if not (is_supergiant or is_rare_type or is_nearby):
        return None

    parts: list[str] = []
    if temp_label and lum_label:
        raw = f"{temp_label} {lum_label}"
    elif temp_label:
        raw = f"{temp_label} star"
    else:
        raw = lum_label  # type: ignore[assignment]
    parts.append(raw[0].upper() + raw[1:])

    if absmag is not None:
        l_sun = 10 ** ((4.83 - absmag) / 2.5)
        if l_sun >= 50:
            parts.append(f"~{_lsun_str(l_sun)}\u00d7 the Sun's luminosity")

    if is_nearby and dist is not None:
        ly = dist * 3.2616
        parts.append(f"{ly:.1f} light-years from Earth")

    return "; ".join(parts)


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
        stars, n_curated, n_auto = self._process(csv_paths, var_index or {}, notes)
        if attach_double:
            n_dbl_stars, n_dbl_pairs = self._double_matcher.attach(
                stars,
                max_mag=self._max_mag,
                min_sep=self._min_double_star_sep,
            )
        else:
            n_dbl_stars = 0
            n_dbl_pairs = 0
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
            star["note"] = notes[hip]
            return star, 1, 0
        absmag = _float_or_none(row.get("absmag", ""))
        auto = _auto_note(star.get("spect", "") or "", absmag, star.get("dist"))
        if auto:
            star["note"] = auto
            if absmag is not None:
                l_sun = 10 ** ((4.83 - absmag) / 2.5)
                if l_sun >= 50:
                    phrase = f"~{_lsun_str(l_sun)}\u00d7 the Sun's luminosity"
                    if phrase in auto:
                        star["_lsun"] = l_sun
                        star["_lsun_phrase"] = phrase
            return star, 0, 1
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
        self._cap_luminosity_notes(stars)
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
            phrase = s.pop("_lsun_phrase")
            s["note"] = (
                s["note"]
                .replace(f"; {phrase}", "")
                .replace(f"{phrase}; ", "")
            )
            s.pop("_lsun", None)
        for s in tagged[:top_n]:
            s.pop("_lsun", None)
            s.pop("_lsun_phrase", None)

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
            print(f"Stars included : {len(stars):,} across {len(grouped):,} constellations")
            if show_variables:
                print(f"Variable stars : {n_variable} encoded with amplitude \u2265 {self._var_threshold}")
            if show_double:
                print(
                    f"Double stars   : {n_dbl_stars} stars with {n_dbl_pairs} pairs "
                    f"(sep >= {self._min_double_star_sep} arcsec)"
                )
            print(f"Star notes     : {notes_summary}")
            print(f"Output         : {out} ({size_mb:.2f} MB)")
        return out
    # pylint: enable=too-many-arguments,too-many-positional-arguments,too-many-locals
