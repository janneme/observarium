"""Unit tests for the comet pipeline (comets.py).

Fixture lines below are real records copied verbatim from a live download of
MPC's CometEls.txt, used to validate the fixed-width column parsing against
actual data rather than a synthesized/guessed layout.
"""

import pytest

from comets import _estimate_peak_magnitude, _parse_comet_line, _to_julian_date

_HALLEY_LINE = (
    "0001P         2061 08  4.0925  0.571157  0.968018  112.2184   59.3184  "
    "162.1842  20260727   5.5  3.2  1P/Halley                                "
    "                MPC191592"
)
_ENCKE_LINE = (
    "0002P         2027 02 10.2288  0.338638  0.847306  187.2858  334.0194   "
    "11.3479  20260727  11.5  6.0  2P/Encke                                  "
    "               MPC191592"
)
_UNNUMBERED_LINE = (
    "    CJ42E00A  2028 09 13.9472  1.278072  0.934934  335.5437  172.3237   "
    "37.8789  20260727  13.5  4.0  C/1942 EA (Vaisala)                       "
    "               MPEC 2026-K60"
)


def test_to_julian_date_j2000_epoch():
    """2000-01-01 12:00 TT is the defining epoch, JD 2451545.0 exactly."""
    assert _to_julian_date(2000, 1, 1, 0.5) == pytest.approx(2451545.0, abs=1e-9)


def test_parse_comet_line_halley():
    result = _parse_comet_line(_HALLEY_LINE)

    assert result is not None
    assert result["name"] == "1P/Halley"
    assert result["designation"] == "0001P"
    assert result["q"] == pytest.approx(0.571157, abs=1e-6)
    assert result["e"] == pytest.approx(0.968018, abs=1e-6)
    assert result["argOfPeriDeg"] == pytest.approx(112.2184, abs=1e-4)
    assert result["ascNodeDeg"] == pytest.approx(59.3184, abs=1e-4)
    assert result["inclDeg"] == pytest.approx(162.1842, abs=1e-4)
    assert result["H"] == pytest.approx(5.5, abs=1e-6)
    assert result["slopeN"] == pytest.approx(3.2, abs=1e-6)
    # Perihelion passage 2061-08-04.0925 TT
    assert result["tpJd"] == pytest.approx(2474040.5925, abs=1e-4)


def test_parse_comet_line_encke():
    result = _parse_comet_line(_ENCKE_LINE)

    assert result is not None
    assert result["name"] == "2P/Encke"
    assert result["designation"] == "0002P"
    assert result["q"] == pytest.approx(0.338638, abs=1e-6)
    assert result["e"] == pytest.approx(0.847306, abs=1e-6)
    assert result["H"] == pytest.approx(11.5, abs=1e-6)
    assert result["slopeN"] == pytest.approx(6.0, abs=1e-6)


def test_parse_comet_line_unnumbered_uses_name_as_designation():
    """Unnumbered comets have a blank periodic-number field."""
    result = _parse_comet_line(_UNNUMBERED_LINE)

    assert result is not None
    assert result["name"] == "C/1942 EA (Vaisala)"
    assert result["designation"] == "C/1942 EA (Vaisala)"
    assert result["e"] == pytest.approx(0.934934, abs=1e-6)


def test_parse_comet_line_invalid():
    assert _parse_comet_line("") is None
    assert _parse_comet_line("Too short") is None
    assert _parse_comet_line(" " * 200) is None


def test_estimate_peak_magnitude_halley_bright_enough_to_include():
    """Halley (H=5.5, n=3.2, q=0.571) should estimate well under mag 9."""
    mag = _estimate_peak_magnitude(5.5, 3.2, 0.571157)
    assert mag < 9.0


def test_estimate_peak_magnitude_scales_with_q():
    """A more distant perihelion (q>1, farther from both Sun and Earth) should
    mean a fainter (higher) estimated peak magnitude, all else equal."""
    near = _estimate_peak_magnitude(10.0, 4.0, 1.5)
    far = _estimate_peak_magnitude(10.0, 4.0, 3.0)
    assert far > near


def test_estimate_peak_magnitude_slope_direction_depends_on_q():
    """The slope term is 2.5*n*log10(r): for q>1 (log10(r)>0) a steeper slope
    makes the estimate fainter; for q<1 (log10(r)<0) it makes it brighter,
    since q<1 means the comet is being evaluated closer to the Sun than 1 AU
    and a larger n amplifies that brightening."""
    base_far = _estimate_peak_magnitude(10.0, 4.0, 2.0)
    steeper_far = _estimate_peak_magnitude(10.0, 8.0, 2.0)
    assert steeper_far > base_far

    base_near = _estimate_peak_magnitude(10.0, 4.0, 0.5)
    steeper_near = _estimate_peak_magnitude(10.0, 8.0, 0.5)
    assert steeper_near < base_near
