"""Unit tests for solar system pipeline (asteroids.py)."""

import gzip
import json
from pathlib import Path

import pytest

from asteroids import (
    SolarSystemPipeline,
    _compute_magnitude_range,
    _estimate_opposition_magnitude,
    _get_planet_catalog,
    _parse_mpcorb_line,
)


def test_parse_mpcorb_line_ceres():
    """Test parsing a real MPCORB line for (1) Ceres."""
    # Real single-line format from MPCORB.DAT (line is ~200+ chars)
    line = (
        "00001    3.34  0.15 K25BL 231.53974   73.29974   80.24964   10.58789  "
        "0.0795764  0.21429712   2.7656157  0 MPO980521  7297 126 1801-2026 0.83 "
        "M-v 30k Veres      4000      (1) Ceres              20260103\n"
    )

    result = _parse_mpcorb_line(line)

    assert result is not None
    assert result["dsg"] == "1"  # Leading zeros stripped
    assert result["name"] == "Ceres"  # No designation prefix
    assert result["H"] == pytest.approx(3.34, rel=0, abs=0.01)
    assert result["G"] == pytest.approx(0.15, rel=0, abs=0.01)
    assert result["a"] == pytest.approx(2.7656157, rel=0, abs=1e-6)
    assert result["e"] == pytest.approx(0.0795764, rel=0, abs=1e-6)
    assert result["i"] == pytest.approx(10.58789, rel=0, abs=1e-4)
    assert result["Omega"] == pytest.approx(80.24964, rel=0, abs=1e-4)
    assert result["omega"] == pytest.approx(73.29974, rel=0, abs=1e-4)
    assert result["M"] == pytest.approx(231.53974, rel=0, abs=1e-4)
    # Check magnitude range is present and reasonable
    assert "min_mag" in result
    assert "max_mag" in result
    assert result["min_mag"] < result["max_mag"]


def test_parse_mpcorb_line_vesta():
    """Test parsing a real MPCORB line for (4) Vesta."""
    line = (
        "00004    3.25  0.15 K25BL  26.80969  151.53711  103.70232    7.14406  "
        "0.0901676  0.27158812   2.3615413  0 MPO964264  7603 112 1821-2025 0.69 "
        "M-p 18k MPCORBFIT  4000      (4) Vesta              20250624\n"
    )

    result = _parse_mpcorb_line(line)

    assert result is not None
    assert result["dsg"] == "4"
    assert result["name"] == "Vesta"
    assert result["H"] == pytest.approx(3.25, rel=0, abs=0.01)
    assert result["a"] == pytest.approx(2.3615413, rel=0, abs=1e-6)


def test_parse_mpcorb_line_invalid():
    """Test that invalid lines return None."""
    assert _parse_mpcorb_line("") is None
    assert _parse_mpcorb_line("Too short") is None
    assert _parse_mpcorb_line("x" * 200) is None


def test_get_planet_catalog():
    """Test that planet catalog has correct structure."""
    sources_dir = Path(__file__).parent.parent / "sources"
    planets = _get_planet_catalog(sources_dir)

    # Should have 7 observable major planets (excludes Earth and Pluto)
    assert len(planets) == 7

    # Check first and last
    assert planets[0]["name"] == "Mercury"
    assert planets[0]["inner"] is True
    assert planets[-1]["name"] == "Neptune"
    assert planets[-1]["inner"] is False

    # Verify all have required fields
    for planet in planets:
        assert "name" in planet
        assert "symbol" in planet
        assert "color" in planet
        assert "inner" in planet
        assert "min_mag" in planet
        assert "max_mag" in planet
        assert planet["min_mag"] <= planet["max_mag"]


def test_estimate_opposition_magnitude():
    """Test opposition magnitude estimation."""
    # Ceres: H=3.53, a=2.77 AU
    # At favorable opposition: ~6.7 to 7.4 mag
    mag = _estimate_opposition_magnitude(3.53, 2.77)
    assert 6.0 < mag < 8.0

    # Vesta: H=3.20, a=2.36 AU
    # Brighter due to smaller distance
    mag_vesta = _estimate_opposition_magnitude(3.20, 2.36)
    assert mag_vesta < mag  # Vesta should be brighter than Ceres
    assert 5.0 < mag_vesta < 7.0


def test_compute_magnitude_range():
    """Test magnitude range computation at perihelion/aphelion opposition."""
    # Vesta: H=3.25, a=2.36 AU, e=0.09
    min_mag, max_mag = _compute_magnitude_range(3.25, 2.36, 0.09)

    # min_mag should be brighter (lower number) than max_mag
    assert min_mag < max_mag

    # Reasonable range for Vesta (roughly 5.2 to 6.3 mag)
    assert 5.0 < min_mag < 5.5
    assert 6.0 < max_mag < 6.5

    # Higher eccentricity should increase the range
    min_low_e, max_low_e = _compute_magnitude_range(3.25, 2.36, 0.05)
    min_high_e, max_high_e = _compute_magnitude_range(3.25, 2.36, 0.20)
    assert (max_high_e - min_high_e) > (max_low_e - min_low_e)


def _write_fixture_mpcorb(mpcorb_path: Path) -> None:
    """Write a minimal MPCORB.DAT.gz fixture with a few test asteroids."""
    header = (
        "MINOR PLANET CENTER ORBIT DATABASE (MPCORB)\n"
        "Des'n     H     G   Epoch     M        Peri.      Node       Incl.  "
        "     e            n           a        Reference #Obs #Opp    Arc    "
        "rms  Perts   Computer\n\n"
        "--------------------------------------------------------------------"
        "--------------------\n"
        "--------------------------------------------------------------------"
        "--------------------\n"
    )

    # Real single-line format for each asteroid (one long line ~200+ chars)
    # Ceres: H=3.34, should pass filter
    ceres = (
        "00001    3.34  0.15 K25BL 231.53974   73.29974   80.24964   10.58789  "
        "0.0795764  0.21429712   2.7656157  0 MPO980521  7297 126 1801-2026 0.83 "
        "M-v 30k Veres      4000      (1) Ceres              20260103\n"
    )

    # Pallas: H=4.12, should pass filter
    pallas = (
        "00002    4.12  0.15 K25BL 211.52976  310.93340  172.88859   34.92833  "
        "0.2306430  0.21379713   2.7699258  0 MPO980521  9062 123 1804-2025 0.77 "
        "M-c 28k MPCORBFIT  4000      (2) Pallas             20251214\n"
    )

    # Vesta: H=3.25, should pass filter (brightest)
    vesta = (
        "00004    3.25  0.15 K25BL  26.80969  151.53711  103.70232    7.14406  "
        "0.0901676  0.27158812   2.3615413  0 MPO964264  7603 112 1821-2025 0.69 "
        "M-p 18k MPCORBFIT  4000      (4) Vesta              20250624\n"
    )

    # Iris: H=5.70, should pass filter with max_mag=9.0
    iris = (
        "00007    5.70  0.15 K25BL  61.72501  145.48205  259.49459    5.51882  "
        "0.2302133  0.26733389   2.3865290  0 MPO980521  5462  92 1848-2026 0.83 "
        "M-v 3Ek MPCORBFIT  0000      (7) Iris               20260411\n"
    )

    # Dim asteroid: H=15.0, should be filtered out
    dim = (
        "99999   15.00  0.15 K25BL  50.00000   50.00000   50.00000    5.00000  "
        "0.1000000  0.50000000   2.5000000  0 MPO000000   100  10 2000-2010 0.50 "
        "M-v 10h MPCW       0000      Dim Test               20260513\n"
    )

    mpcorb_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(mpcorb_path, "wt", encoding="utf-8") as f:
        f.write(header)
        f.write(ceres)
        f.write(pallas)
        f.write(vesta)
        f.write(iris)
        f.write(dim)


def _write_fixture_planets(sources_dir: Path) -> None:
    """Write planets.json fixture for testing."""
    planets_json = sources_dir / "planets.json"
    planets_json.parent.mkdir(parents=True, exist_ok=True)

    planets = [
        {
            "name": "Mercury",
            "symbol": "☿",
            "color": "#A0A0A0",
            "inner": True,
            "min_mag": -2.6,
            "max_mag": 5.7,
        },
        {
            "name": "Venus",
            "symbol": "♀",
            "color": "#FFC649",
            "inner": True,
            "min_mag": -4.9,
            "max_mag": -2.9,
        },
        {
            "name": "Mars",
            "symbol": "♂",
            "color": "#E27B58",
            "inner": True,
            "min_mag": -2.9,
            "max_mag": 1.8,
        },
        {
            "name": "Jupiter",
            "symbol": "♃",
            "color": "#C88B3A",
            "inner": False,
            "min_mag": -2.9,
            "max_mag": -1.6,
        },
        {
            "name": "Saturn",
            "symbol": "♄",
            "color": "#FAD5A5",
            "inner": False,
            "min_mag": -0.5,
            "max_mag": 1.5,
        },
        {
            "name": "Uranus",
            "symbol": "♅",
            "color": "#4FD0E7",
            "inner": False,
            "min_mag": 5.3,
            "max_mag": 6.0,
        },
        {
            "name": "Neptune",
            "symbol": "♆",
            "color": "#4166F5",
            "inner": False,
            "min_mag": 7.8,
            "max_mag": 8.0,
        },
    ]

    with planets_json.open("w", encoding="utf-8") as f:
        json.dump(planets, f, indent=2, ensure_ascii=False)


def test_solar_system_pipeline_filters_and_writes(tmp_path: Path):
    """Test that the solar system pipeline generates planets and minor_planets."""
    sources = tmp_path / "sources"
    cache = tmp_path / "cache"
    outdir = tmp_path / "output"
    sources.mkdir()
    cache.mkdir()

    mpcorb_path = cache / "MPCORB.DAT.gz"
    _write_fixture_mpcorb(mpcorb_path)
    _write_fixture_planets(sources)

    pipeline = SolarSystemPipeline(sources, outdir, cache_dir=cache)
    output = pipeline.run(max_mag=9.0)

    assert output.exists()
    assert output.name == "solar_system.json"
    data = json.loads(output.read_text(encoding="utf-8"))

    # Check top-level structure
    assert "planets" in data
    assert "minor_planets" in data

    # Check planets section
    assert len(data["planets"]) == 7
    assert data["planets"][0]["name"] == "Mercury"
    assert data["planets"][-1]["name"] == "Neptune"

    # Check minor_planets section (should have Ceres, Pallas, Vesta, Iris)
    minor_planets = data["minor_planets"]
    assert len(minor_planets) == 4

    # Check they're sorted by H (brightest first)
    assert minor_planets[0]["name"] == "Vesta"  # H=3.25
    assert minor_planets[1]["name"] == "Ceres"  # H=3.34
    assert minor_planets[2]["name"] == "Pallas"  # H=4.12
    assert minor_planets[3]["name"] == "Iris"  # H=5.70

    # Verify Ceres has all required fields
    ceres = next(a for a in minor_planets if a["name"] == "Ceres")
    assert ceres["dsg"] == "1"
    assert ceres["H"] == pytest.approx(3.34, rel=0, abs=0.01)
    assert ceres["G"] == pytest.approx(0.15, rel=0, abs=0.01)
    assert ceres["a"] == pytest.approx(2.7656157, rel=0, abs=1e-6)
    assert ceres["e"] == pytest.approx(0.0795764, rel=0, abs=1e-6)
    assert "i" in ceres
    assert "Omega" in ceres
    assert "omega" in ceres
    assert "M" in ceres
    assert "epoch" in ceres
    assert "min_mag" in ceres
    assert "max_mag" in ceres


def test_solar_system_pipeline_honours_max_mag_override(tmp_path: Path):
    """Test that max_mag parameter correctly filters minor planets."""
    sources = tmp_path / "sources"
    cache = tmp_path / "cache"
    outdir = tmp_path / "output"
    sources.mkdir()
    cache.mkdir()

    mpcorb_path = cache / "MPCORB.DAT.gz"
    _write_fixture_mpcorb(mpcorb_path)
    _write_fixture_planets(sources)

    pipeline = SolarSystemPipeline(sources, outdir, cache_dir=cache)

    # With max_mag=7.0, should get only Ceres and Vesta (not Pallas or Iris)
    # Estimated magnitudes: Vesta ~5.8, Ceres ~6.8, Pallas ~7.6, Iris ~8.3
    output = pipeline.run(max_mag=7.0)
    data = json.loads(output.read_text(encoding="utf-8"))

    minor_planets = data["minor_planets"]
    assert len(minor_planets) == 2
    names = [a["name"] for a in minor_planets]
    assert "Ceres" in names
    assert "Vesta" in names
    assert "Pallas" not in names
    assert "Iris" not in names
