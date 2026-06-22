"""Solar system pipeline: planet metadata + MPC Orbit Database → solar_system.json."""

import gzip
import json
import math
import re
from pathlib import Path
from typing import Any

from config import ASTEROID_MAX_MAGNITUDE, MPCORB_FILENAME, MPCORB_URL
from downloader import Downloader


def _compute_magnitude_range(
    abs_mag: float, semimajor_axis_au: float, eccentricity: float
) -> tuple[float, float]:
    """Compute apparent magnitude range at opposition.

    Returns (min_mag, max_mag) where min_mag is brightest (perihelion opposition)
    and max_mag is dimmest (aphelion opposition).

    Uses simplified opposition geometry:
        V = H + 5*log10(r * Δ)
    where r = heliocentric distance, Δ = geocentric distance.

    Args:
        abs_mag: Absolute magnitude H.
        semimajor_axis_au: Semi-major axis in AU.
        eccentricity: Orbital eccentricity.

    Returns:
        Tuple of (min_mag, max_mag) - apparent magnitude at brightest and dimmest.
    """
    # Perihelion and aphelion distances from Sun
    r_peri = semimajor_axis_au * (1.0 - eccentricity)
    r_aph = semimajor_axis_au * (1.0 + eccentricity)

    # At opposition, Earth-asteroid distance ≈ |r - 1.0|
    # (Earth's orbit = 1.0 AU, assuming circular)
    delta_peri = abs(r_peri - 1.0)
    delta_aph = abs(r_aph - 1.0)

    # Apparent magnitude at perihelion opposition (brightest)
    min_mag = abs_mag + 5.0 * math.log10(r_peri * delta_peri)

    # Apparent magnitude at aphelion opposition (dimmest)
    max_mag = abs_mag + 5.0 * math.log10(r_aph * delta_aph)

    return (min_mag, max_mag)


def _estimate_opposition_magnitude(abs_mag: float, semimajor_axis_au: float) -> float:
    """Estimate apparent magnitude at opposition for an asteroid.

    Uses a simplified formula assuming favorable opposition geometry.
    For asteroids beyond Earth's orbit:
        V ≈ H + 5*log10((a-1)*a)
    where a is semi-major axis in AU and H is absolute magnitude.

    Args:
        abs_mag: Absolute magnitude H (magnitude at 1 AU from Sun and Earth).
        semimajor_axis_au: Semi-major axis in AU.

    Returns:
        Estimated apparent magnitude at favorable opposition.
    """
    if semimajor_axis_au <= 1.0:
        # For near-Earth asteroids, use a conservative estimate
        return abs_mag + 5.0 * math.log10(max(0.1, semimajor_axis_au) * 2.0)
    # Main belt and beyond
    distance_at_opposition = abs(semimajor_axis_au - 1.0)
    return abs_mag + 5.0 * math.log10(distance_at_opposition * semimajor_axis_au)


def _extract_orbital_elements(line: str) -> dict[str, Any] | None:
    """Extract orbital elements from fixed-width MPCORB columns.

    Columns (1-indexed):
        1-7:   Designation (packed or numbered)
        9-13:  Absolute magnitude H
        15-19: Slope parameter G
        21-25: Epoch (packed date)
        27-35: Mean anomaly M (degrees)
        38-46: Argument of perihelion ω (degrees)
        49-57: Longitude of ascending node Ω (degrees)
        60-68: Inclination i (degrees)
        71-79: Eccentricity e
        93-103: Semi-major axis a (AU)

    Returns None if required fields (H or a) are missing or unparseable.
    """
    h_str = line[8:13].strip()
    sma_str = line[92:103].strip()
    if not h_str or not sma_str:
        return None

    def _f(s: str, default: float = 0.0) -> float:
        return float(s) if s else default

    return {
        "H": float(h_str),
        "G": _f(line[14:19].strip(), default=0.15),  # IAU default G=0.15
        "epoch": line[20:25].strip(),
        "M": _f(line[26:35].strip()),
        "omega": _f(line[37:46].strip()),
        "Omega": _f(line[48:57].strip()),
        "i": _f(line[59:68].strip()),
        "e": _f(line[70:79].strip()),
        "a": float(sma_str),
    }


def _parse_mpcorb_line(line: str) -> dict[str, Any] | None:
    """Parse one line from MPCORB.DAT.

    Format reference: https://www.minorplanetcenter.net/iau/info/MPOrbitFormat.html

    Returns:
        Dict with orbital elements, or None if line cannot be parsed.
    """
    if len(line) < 103:
        return None

    try:
        designation = line[0:7].strip()
        if not designation:
            return None

        elements = _extract_orbital_elements(line)
        if elements is None:
            return None

        # Name: "(4) Vesta              20250624" → "Vesta"
        name_raw = line[165:].strip() if len(line) > 165 else designation
        name_with_dsg = re.sub(r'\s+\d{8}$', '', name_raw) if name_raw else designation
        name_match = re.match(r'^\([^)]+\)\s+(.+)$', name_with_dsg)
        name = name_match.group(1) if name_match else name_with_dsg

        dsg = designation.lstrip('0') or '0'
        min_mag, max_mag = _compute_magnitude_range(elements["H"], elements["a"], elements["e"])

        return {
            "dsg": dsg,
            "name": name,
            **elements,
            "min_mag": round(min_mag, 1),
            "max_mag": round(max_mag, 1),
        }
    except (ValueError, IndexError):
        return None


def _get_planet_catalog(sources_dir: Path) -> list[dict[str, Any]]:
    """Read planet metadata from sources/planets.json.

    Args:
        sources_dir: Directory containing planets.json.

    Returns:
        List of 7 observable major planet records (excludes Earth and Pluto).
    """
    planets_file = sources_dir / "planets.json"

    with planets_file.open("r", encoding="utf-8") as f:
        planets = json.load(f)

    return planets


class SolarSystemPipeline:
    """Generate solar_system.json: planet metadata + minor-planet orbital elements."""

    def __init__(
        self,
        sources_dir: Path,
        output_dir: Path,
        cache_dir: Path | None = None,
        debug: bool = False,
    ) -> None:
        self._sources_dir = sources_dir
        self._output_dir = output_dir
        self._debug = debug
        cache = cache_dir or sources_dir
        self._downloader = Downloader(cache, debug=debug)

    def run(self, max_mag: float | None = None) -> Path:
        """Execute full pipeline and return output path.

        Args:
            max_mag: Maximum apparent magnitude at opposition for minor planets.

        Returns:
            Path to solar_system.json.
        """
        source = self._downloader.fetch(MPCORB_URL, MPCORB_FILENAME)
        minor_planets = self._process_minor_planets(source, max_mag=max_mag)
        planets = _get_planet_catalog(self._sources_dir)
        output = self._write(planets, minor_planets)
        self._print_summary(planets, minor_planets, output, max_mag)
        return output

    def _print_summary(
        self,
        planets: list[dict[str, Any]],
        minor_planets: list[dict[str, Any]],
        output_path: Path,
        max_mag: float | None,
    ) -> None:
        """Print concise pipeline summary similar to other data-prep commands."""
        cutoff = ASTEROID_MAX_MAGNITUDE if max_mag is None else max_mag
        size_mb = output_path.stat().st_size / 1_048_576
        print(f"Planets       : {len(planets)} loaded from sources/planets.json")
        print(f"Asteroids     : {len(minor_planets):,} with opposition mag <= {cutoff:g}")
        print(f"Output        : {output_path} ({size_mb:.2f} MB)")

    def _process_minor_planets(
        self,
        source: Path,
        max_mag: float | None = None,
    ) -> list[dict[str, Any]]:
        """Parse MPCORB.DAT.gz and filter bright minor planets (asteroids).

        MPCORB format: each asteroid is one long line.

        Args:
            source: Path to MPCORB.DAT.gz file.
            max_mag: Maximum apparent magnitude at opposition.

        Returns:
            List of minor-planet records with orbital elements.
        """
        cutoff = ASTEROID_MAX_MAGNITUDE if max_mag is None else max_mag
        asteroids: list[dict[str, Any]] = []

        with gzip.open(source, "rt", encoding="utf-8", errors="ignore") as f:
            # Skip header lines until we hit the separator line
            for line in f:
                if line.startswith("-------"):
                    break

            # Now process data lines (one line per asteroid)
            for line in f:
                if not line.strip():
                    # Empty line separates sections; skip
                    continue

                record = _parse_mpcorb_line(line)
                if record is None:
                    continue

                # Estimate apparent magnitude at opposition
                est_mag = _estimate_opposition_magnitude(record["H"], record["a"])

                # Also apply a sanity check based on absolute magnitude H.
                # Asteroids with H > 8.0 are unlikely to reach mag 9.0 at opposition
                # in realistic viewing conditions (unless very close approaches).
                if est_mag <= cutoff and record["H"] <= 8.0:
                    asteroids.append(record)

        # Sort by H (brightest first)
        asteroids.sort(key=lambda x: x["H"])

        return asteroids

    def _write(
        self, planets: list[dict[str, Any]], minor_planets: list[dict[str, Any]]
    ) -> Path:
        """Write solar system data to JSON output file.

        Args:
            planets: List of planet metadata records.
            minor_planets: List of minor-planet (asteroid) orbital element records.

        Returns:
            Path to solar_system.json.
        """
        self._output_dir.mkdir(parents=True, exist_ok=True)
        output_path = self._output_dir / "solar_system.json"

        data = {"planets": planets, "minor_planets": minor_planets}

        with output_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

        return output_path
