"""Star catalogue pipeline: HYG v4 CSV → data_prep/output/stars.json."""

import csv
import gzip
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config import (
    ATHYG_FILENAME,
    ATHYG_FULL_FILENAMES,
    ATHYG_FULL_MAG_THRESHOLD,
    ATHYG_FULL_URLS,
    ATHYG_URL,
    BRIGHT_VARIABLE_THRESHOLD,
    EUROPE_MIN_DEC,
    EXTREME_STARS_NUM,
    GAIA_DEFAULT_MAX_MAG,
    GAIA_FILENAME_TEMPLATE,
    GAIA_MAG_THRESHOLD,
    MAX_STAR_MAGNITUDE,
)
from double_stars import DoubleStarMatcher
from downloader import Downloader
from gaia import fetch_gaia, load_gaia_stars
from star_annotations import _StarAnnotationsMixin

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


def _mag_sort(s: dict[str, Any]) -> float:
    m = s["mag"]
    return m[0] if isinstance(m, list) else m


def _encode_mag(m: Any) -> str:
    if isinstance(m, list):
        return f"{m[0]:.2f}:{m[1]:.2f}"
    return f"{m:.2f}"


def _col_idx(s: dict[str, Any]) -> int:
    return _COLOUR_TO_IDX.get(s.get("clr", ""), len(COLOR_PALETTE) - 1)


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


def _load_alt_names(path: Path) -> dict[int, list[str]]:
    """Return a HIP → [alt_name, ...] mapping loaded from a CSV sidecar file.

    One row per alt name; a HIP may have several rows. Returns an empty dict
    when the file is absent (alt names are optional).
    """
    if not path.exists():
        return {}
    alt_names: dict[int, list[str]] = {}
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            hip = _int_or_none(row.get("hip", ""))
            alt_name = row.get("alt_name", "").strip()
            if hip and alt_name:
                alt_names.setdefault(hip, []).append(alt_name)
    return alt_names


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


def variable_threshold(mag: float, bright_threshold: float = BRIGHT_VARIABLE_THRESHOLD) -> float:
    """Return the magnitude-dependent variability amplitude threshold.

    T(m) = bright_threshold * (1 + 2 * (m / 10)³)

    Very flat at the bright end, accelerating toward faint magnitudes.
    Reaches 3 × bright_threshold at m = 10.
    """
    return bright_threshold * (1 + 2 * (mag / 10) ** 3)


def _is_variable(
    var_min: float | None,
    var_max: float | None,
    threshold: float,
) -> bool:
    """Return True when the magnitude range meets or exceeds *threshold*."""
    if var_min is None or var_max is None:
        return False
    return (var_max - var_min) >= threshold


def _star_mag_fields(
    mag: float,
    var_range: tuple[float, float] | None,
    var_threshold: float,
    var_type: str | None,
    period: float | None,
) -> dict[str, Any]:
    """Return the mag-related star fields: `mag` (scalar or [min, max] for a
    variable star), plus `var_type`/`var_period` when the star is variable."""
    eff_threshold = variable_threshold(mag, var_threshold)
    mag_value: float | list[float] = (
        [var_range[0], var_range[1]]
        if var_range is not None and _is_variable(var_range[0], var_range[1], eff_threshold)
        else mag
    )
    fields: dict[str, Any] = {"mag": mag_value}
    if isinstance(mag_value, list):
        if var_type:
            fields["var_type"] = var_type
        if period is not None:
            fields["var_period"] = period
    return fields


def _build_star(
    row: dict[str, str],
    max_mag: float = MAX_STAR_MAGNITUDE,
    min_dec: float = EUROPE_MIN_DEC,
    var_range: tuple[float, float] | None = None,
    var_threshold: float = BRIGHT_VARIABLE_THRESHOLD,
    var_type: str | None = None,
    period: float | None = None,
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
    star: dict[str, Any] = {
        "pos": [ra, dec],
        "clr": spectral_colour(spect),
        **_star_mag_fields(mag, var_range, var_threshold, var_type, period),
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
# Row-level enrichment data bundle — threaded through _process/_process_file/
# _process_row instead of three separate parameters each.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _EnrichmentData:
    var_index: dict[int, tuple]
    notes: dict[int, str]
    alt_names: dict[int, list[str]]


# ---------------------------------------------------------------------------
# Pipeline class
# ---------------------------------------------------------------------------


class StarPipeline(_StarAnnotationsMixin):
    """Downloads HYG v4, filters stars, and writes stars.json."""

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        sources_dir: Path,
        output_dir: Path,
        cache_dir: Path | None = None,
        max_mag: float = MAX_STAR_MAGNITUDE,
        var_threshold: float = BRIGHT_VARIABLE_THRESHOLD,
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

    def _fetch_athyg_csv_paths(self) -> list[Path]:
        if self._max_mag > ATHYG_FULL_MAG_THRESHOLD:
            return [
                self._downloader.fetch(url, name)
                for url, name in zip(ATHYG_FULL_URLS, ATHYG_FULL_FILENAMES, strict=True)
            ]
        return [self._downloader.fetch(ATHYG_URL, ATHYG_FILENAME)]

    def _supplement_with_gaia(self, stars: list[dict[str, Any]]) -> None:
        """Append Gaia DR3 stars above the AT-HYG/Tycho-2 ceiling, in place."""
        if self._max_mag <= GAIA_MAG_THRESHOLD:
            return
        gaia_max = min(self._max_mag, GAIA_DEFAULT_MAX_MAG)
        fname = GAIA_FILENAME_TEMPLATE.format(max_mag=gaia_max, min_dec=EUROPE_MIN_DEC)
        gaia_cache = self._downloader.cache_dir / fname
        fetch_gaia(gaia_max, EUROPE_MIN_DEC, gaia_cache, min_mag=GAIA_MAG_THRESHOLD)
        gaia_stars = load_gaia_stars(gaia_cache, gaia_max, EUROPE_MIN_DEC, COLOR_PALETTE)
        print(f"Gaia supplement : {len(gaia_stars):,} stars loaded")
        stars.extend(gaia_stars)

    def _attach_double_stars(
        self, stars: list[dict[str, Any]], attach_double: bool
    ) -> tuple[int, int, int, int]:
        """Optionally attach double-star metadata; return the four double-star counts."""
        if not attach_double:
            return 0, 0, 0, 0
        n_dbl_stars, n_dbl_pairs, n_phys_pairs = self._double_matcher.attach(
            stars,
            max_mag=self._max_mag,
            min_sep=self._min_double_star_sep,
        )
        n_apparent_pairs = self._double_matcher.classify_apparent_pairs(stars)
        return n_dbl_stars, n_dbl_pairs, n_phys_pairs, n_apparent_pairs

    def run(
        self,
        var_index: dict[int, tuple] | None = None,
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
        csv_paths = self._fetch_athyg_csv_paths()
        enrichment = _EnrichmentData(
            var_index=var_index or {},
            notes=_load_notes(self._sources_dir / "notes_stars.csv"),
            alt_names=_load_alt_names(self._sources_dir / "star_alt_names.csv"),
        )
        stars, n_curated, _ = self._process(csv_paths, enrichment)

        # Gaia DR3 supplement — fills the gap above the AT-HYG / Tycho-2 ceiling
        self._supplement_with_gaia(stars)

        # Compute luminosities and annotate the most luminous stars. Recompute
        # the post-annotation auto-note count so only the top N are reported
        # as auto-generated notes.
        top_n = extreme_stars_num if extreme_stars_num is not None else EXTREME_STARS_NUM
        n_auto = self._run_annotation_passes(stars, var_index, top_n)

        n_dbl_stars, n_dbl_pairs, n_phys_pairs, n_apparent_pairs = self._attach_double_stars(
            stars, attach_double
        )
        self._write_csv(stars)
        return self._write(
            stars,
            n_curated,
            n_auto,
            n_dbl_stars,
            n_dbl_pairs,
            n_phys_pairs,
            n_apparent_pairs,
            show_variables=(bool(var_index) and (show_summary or self._debug)),
            show_double=(attach_double and (show_summary or self._debug)),
            show_summary=show_summary,
        )

    def _process_row(
        self,
        row: dict[str, str],
        enrichment: _EnrichmentData,
    ) -> tuple[dict[str, Any] | None, int, int]:
        """Process one CSV row; return (star_or_None, n_curated_delta, n_auto_delta)."""
        hip = _int_or_none(row.get("hip", ""))
        var_data = enrichment.var_index.get(hip) if hip else None
        var_range = (var_data[0], var_data[1]) if var_data else None
        var_type = var_data[2] if var_data and len(var_data) > 2 else None
        period = var_data[3] if var_data and len(var_data) > 3 else None
        star = _build_star(
            row,
            max_mag=self._max_mag,
            var_range=var_range,
            var_threshold=self._var_threshold,
            var_type=var_type,
            period=period,
        )
        if star is None:
            return None, 0, 0
        if hip and hip in enrichment.alt_names:
            # Alternate (informal / historical) names, e.g. "Navi" for gamma Cas.
            # Additive field: absent when a star has no curated alt names, so
            # older catalogues without this feature remain unaffected.
            star["altNames"] = enrichment.alt_names[hip]
        if hip and hip in enrichment.notes:
            # Attach curated note into `note` (preserve curated text).
            star["note"] = enrichment.notes[hip]
            star["_curated_note"] = True
            return star, 1, 0
        # Auto-generated physical notes have been disabled. Preserve curated
        # notes only; count no auto notes.
        return star, 0, 0

    def _process_file(
        self,
        csv_path: Path,
        fieldnames: list[str] | None,
        enrichment: _EnrichmentData,
    ) -> tuple[list[dict[str, Any]], int, int, list[str]]:
        """Read one catalogue file; return (stars, n_curated, n_auto, fieldnames)."""
        stars: list[dict[str, Any]] = []
        n_curated = 0
        n_auto = 0
        opener = gzip.open if csv_path.suffix == ".gz" else open
        with opener(csv_path, "rt", encoding="utf-8") as fh:
            reader = csv.DictReader(fh, fieldnames=fieldnames)
            for row in reader:
                star, dc, da = self._process_row(row, enrichment)
                if star is not None:
                    stars.append(star)
                    n_curated += dc
                    n_auto += da
        return stars, n_curated, n_auto, list(reader.fieldnames or [])

    def _process(
        self,
        csv_paths: list[Path],
        enrichment: _EnrichmentData,
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
                enrichment,
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
    def _dbl_csv_nature(s: dict[str, Any]) -> str:
        if not s.get("dbl"):
            return ""
        letters: set[str] = set()
        has_vis = False
        has_phys = False
        for entry in s.get("dbl", []):
            for pair in entry.get("pairs", []):
                if "vis" in pair:
                    has_vis = True
                if "phys" in pair:
                    has_phys = True
                for c in str(pair.get("comp", "")):
                    if "A" <= c <= "Z":
                        letters.add(c)
        if len(letters) > 2:
            return "m"
        if has_vis:
            return "a"
        if has_phys:
            return "p"
        return "1"

    def _write_t1_csv(self, path_t1: Path, tier1: list[dict[str, Any]]) -> None:
        t1_header = "ra,de,mg,cl,hp,hd,sp,ds,pr,pd,fl,by,db,nm,nt,sm,cn,vt,vp,an"
        t1_fixed_cols = 10  # columns before the optional trailing group
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
                    (s.get("spect") or "").replace(",", "")[:2],
                    f"{s['dist']:.1f}" if s.get("dist") is not None else "",
                    f"{s['pm_ra']:.2f}" if s.get("pm_ra") is not None else "",
                    f"{s['pm_dec']:.2f}" if s.get("pm_dec") is not None else "",
                    # optional trailing
                    str(s["flam"]) if s.get("flam") else "",
                    s.get("bay") or "",
                    self._dbl_csv_nature(s),
                    s.get("name") or "",
                    (s.get("note") or "").replace(",", ""),
                    (s.get("smr") or "").replace(",", ""),
                    s.get("const") or "",
                    s.get("var_type") or "",
                    f"{s['var_period']:.6g}" if s.get("var_period") is not None else "",
                    ";".join(s.get("altNames") or []),
                ]
                # Strip trailing empty optional columns to save space.
                while len(row) > t1_fixed_cols and row[-1] == "":
                    row.pop()
                fh.write(",".join(row) + "\n")

    @staticmethod
    def _write_t2_csv(path_t2: Path, tier2: list[dict[str, Any]]) -> None:
        t2_header = "z,ra,de,mg,cl,hp,hd,sp,ds,pr,pd"
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
                    (s.get("spect") or "").replace(",", "")[:2],
                    f"{s['dist']:.1f}" if s.get("dist") is not None else "",
                    f"{s['pm_ra']:.2f}" if s.get("pm_ra") is not None else "",
                    f"{s['pm_dec']:.2f}" if s.get("pm_dec") is not None else "",
                ]
                fh.write(",".join(row) + "\n")

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

        tier1 = sorted([s for s in stars if _mag_sort(s) <= T1_MAG_LIMIT], key=_mag_sort)
        tier2 = sorted(
            [s for s in stars if _mag_sort(s) > T1_MAG_LIMIT],
            key=lambda s: (_compute_zone(s["pos"][0] * 15, s["pos"][1]), _mag_sort(s)),
        )

        self._write_t1_csv(path_t1, tier1)
        self._write_t2_csv(path_t2, tier2)

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
        n_phys_pairs: int,
        n_apparent_pairs: int = 0,
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
                    f"Variable stars : {n_variable} encoded"
                    f" (bright threshold {self._var_threshold},"
                    f" cubic magnitude scaling)"
                )
            if show_double:
                print(
                    f"Double stars   : {n_dbl_stars} stars with {n_dbl_pairs} pairs "
                    f"({n_phys_pairs} physical, {n_apparent_pairs} apparent, "
                    f"sep >= {self._min_double_star_sep} arcsec)"
                )
            print(f"Star notes     : {notes_summary}")
            print(f"Output         : {out} ({size_mb:.2f} MB)")
        return out
    # pylint: enable=too-many-arguments,too-many-positional-arguments,too-many-locals
