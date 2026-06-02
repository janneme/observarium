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


def _parse_mpcorb_line(line: str) -> dict[str, Any] | None:
    """Parse one line from MPCORB.DAT.

    Format reference:
    https://www.minorplanetcenter.net/iau/info/MPOrbitFormat.html

    Each asteroid is on a single long line (~200+ characters).

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
        81-91: Mean daily motion n OR
        93-103: Semi-major axis a (AU) - we use this one
        166-202: Name (rest of line)

    Returns:
        Dict with orbital elements, or None if line cannot be parsed.
    """
    if len(line) < 103:
        return None

    try:
        # Designation (column 1-7, 0-indexed: 0-7)
        designation = line[0:7].strip()
        if not designation:
            return None

        # Absolute magnitude H (column 9-13, 0-indexed: 8-13)
        h_str = line[8:13].strip()
        if not h_str:
            return None
        abs_mag = float(h_str)

        # Slope parameter G (column 15-19, 0-indexed: 14-19)
        g_str = line[14:19].strip()
        slope_g = float(g_str) if g_str else 0.15  # Default G=0.15 per IAU

        # Epoch (column 21-25, 0-indexed: 20-25) - packed format, store as-is
        epoch_str = line[20:25].strip()

        # Mean anomaly M (column 27-35, 0-indexed: 26-35)
        mean_anomaly_str = line[26:35].strip()
        mean_anomaly = float(mean_anomaly_str) if mean_anomaly_str else 0.0

        # Argument of perihelion ω (column 38-46, 0-indexed: 37-46)
        arg_peri_str = line[37:46].strip()
        arg_perihelion = float(arg_peri_str) if arg_peri_str else 0.0

        # Longitude of ascending node Ω (column 49-57, 0-indexed: 48-57)
        lon_node_str = line[48:57].strip()
        lon_asc_node = float(lon_node_str) if lon_node_str else 0.0

        # Inclination i (column 60-68, 0-indexed: 59-68)
        inc_str = line[59:68].strip()
        inclination = float(inc_str) if inc_str else 0.0

        # Eccentricity e (column 71-79, 0-indexed: 70-79)
        ecc_str = line[70:79].strip()
        eccentricity = float(ecc_str) if ecc_str else 0.0

        # Semi-major axis a (column 93-103, 0-indexed: 92-103)
        sma_str = line[92:103].strip()
        if not sma_str:
            return None
        semimajor_axis = float(sma_str)

        # Name (from column 166 onwards, 0-indexed: 165+)
        # Format: "(4) Vesta              20250624" - strip trailing date and designation
        name_raw = line[165:].strip() if len(line) > 165 else designation
        # Remove trailing 8-digit date (YYYYMMDD) and extra spaces
        name_with_dsg = re.sub(r'\s+\d{8}$', '', name_raw) if name_raw else designation
        # Strip designation prefix: "(4) Vesta" → "Vesta"
        name_match = re.match(r'^\([^)]+\)\s+(.+)$', name_with_dsg)
        name = name_match.group(1) if name_match else name_with_dsg

        # Strip leading zeros from designation: "00004" → "4"
        dsg = designation.lstrip('0') or '0'

        # Compute magnitude range at opposition
        min_mag, max_mag = _compute_magnitude_range(abs_mag, semimajor_axis, eccentricity)

        return {
            "dsg": dsg,
            "name": name,
            "H": abs_mag,
            "G": slope_g,
            "min_mag": round(min_mag, 1),
            "max_mag": round(max_mag, 1),
            "epoch": epoch_str,
            "M": mean_anomaly,
            "omega": arg_perihelion,
            "Omega": lon_asc_node,
            "i": inclination,
            "e": eccentricity,
            "a": semimajor_axis,
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
        return self._write(planets, minor_planets)

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
