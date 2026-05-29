"""Star catalogue pipeline: HYG v4 CSV → data_prep/output/stars.json."""

import csv
import gzip
import json
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
        ("sao", _int_or_none(row.get("sao", ""))),
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
        max_mag: float = MAX_STAR_MAGNITUDE,
        var_threshold: float = VARIABLE_THRESHOLD,
        debug: bool = False,
    ) -> None:
        self._sources_dir = sources_dir
        self._output_dir = output_dir
        self._max_mag = max_mag
        self._var_threshold = var_threshold
        self._downloader = Downloader(sources_dir, debug=debug)

    def run(
        self,
        var_index: dict[int, tuple[float, float]] | None = None,
    ) -> Path:
        """Execute the full pipeline and return the path to stars.json.

        *var_index* is an optional HIP → (min_mag, max_mag) mapping supplied
        by :class:`~variable_stars.VariableStarPipeline`. When absent, no
        variable-star encoding is applied.
        """
        if self._max_mag > ATHYG_FULL_MAG_THRESHOLD:
            csv_paths = [
                self._downloader.fetch(url, name)
                for url, name in zip(ATHYG_FULL_URLS, ATHYG_FULL_FILENAMES, strict=True)
            ]
        else:
            csv_paths = [self._downloader.fetch(ATHYG_URL, ATHYG_FILENAME)]
        stars = self._process(csv_paths, var_index or {})
        return self._write(stars)

    def _process(
        self, csv_paths: list[Path], var_index: dict[int, tuple[float, float]]
    ) -> list[dict[str, Any]]:
        """Parse one or more CSV files and return filtered star dicts.

        When multiple files are given (full AT-HYG catalogue split into parts),
        only the first file contains a header row; subsequent parts share the
        same schema and must be read with the header extracted from the first.
        """
        stars: list[dict[str, Any]] = []
        shared_fieldnames: list[str] | None = None
        for idx, csv_path in enumerate(csv_paths):
            opener = gzip.open if csv_path.suffix == ".gz" else open
            with opener(csv_path, "rt", encoding="utf-8") as fh:
                # First file: let DictReader auto-detect the header.
                # Subsequent files: inject the saved fieldnames so that all
                # data lines are read as rows (no header line to skip).
                reader = csv.DictReader(
                    fh,
                    fieldnames=None if idx == 0 else shared_fieldnames,
                )
                for row in reader:
                    hip = _int_or_none(row.get("hip", ""))
                    var_range = var_index.get(hip) if hip else None
                    star = _build_star(
                        row,
                        max_mag=self._max_mag,
                        var_range=var_range,
                        var_threshold=self._var_threshold,
                    )
                    if star is not None:
                        stars.append(star)
                if idx == 0:
                    shared_fieldnames = list(reader.fieldnames or [])
        return stars

    def _write(self, stars: list[dict[str, Any]]) -> Path:
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
        size_mb = out.stat().st_size / 1_048_576
        n_variable = sum(1 for s in stars if isinstance(s.get("mag"), list))
        print(f"Stars included : {len(stars):,} across {len(grouped):,} constellations")
        print(f"Variable stars : {n_variable} encoded with amplitude \u2265 {self._var_threshold}")
        print(f"{filename} size: {size_mb:.2f} MB (uncompressed)")
        print(f"Output path    : {out}")
        return out
