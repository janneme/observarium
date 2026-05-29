"""Unit tests for the star catalogue pipeline (stars.py)."""

import pytest

from stars import _build_star, _is_variable, spectral_colour

# ---------------------------------------------------------------------------
# spectral_colour
# ---------------------------------------------------------------------------


class TestSpectralColour:
    def test_o_type_is_blue(self):
        colour = spectral_colour("O5III")
        r, b = int(colour[1:3], 16), int(colour[5:7], 16)
        assert b > r, "O-type star should be blue-dominant"

    def test_b_type_is_blue(self):
        colour = spectral_colour("B3V")
        r, b = int(colour[1:3], 16), int(colour[5:7], 16)
        assert b > r, "B-type star should be blue-dominant"

    def test_m_type_is_red(self):
        colour = spectral_colour("M4V")
        r, b = int(colour[1:3], 16), int(colour[5:7], 16)
        assert r > b, "M-type star should be red-dominant"

    def test_k_type_is_orange(self):
        colour = spectral_colour("K2III")
        r, g = int(colour[1:3], 16), int(colour[3:5], 16)
        assert r > g, "K-type star should be orange (red > green)"

    def test_unknown_type_returns_white(self):
        assert spectral_colour("Z9") == "#ffffff"

    def test_empty_string_returns_white(self):
        assert spectral_colour("") == "#ffffff"

    def test_case_insensitive(self):
        assert spectral_colour("a1v") == spectral_colour("A1V")

    def test_returns_valid_hex(self):
        for letter in "OBAFGKM":
            colour = spectral_colour(letter)
            assert colour.startswith("#")
            assert len(colour) == 7
            int(colour[1:], 16)  # must parse as hex


# ---------------------------------------------------------------------------
# _is_variable
# ---------------------------------------------------------------------------


class TestIsVariable:
    def test_large_range_is_variable(self):
        assert _is_variable(5.0, 8.5) is True

    def test_small_range_is_not_variable(self):
        assert _is_variable(6.0, 6.5) is False

    def test_exactly_threshold_is_variable(self):
        # range == 1.0 (default threshold), >= is inclusive
        assert _is_variable(4.0, 5.0) is True

    def test_below_threshold_is_not_variable(self):
        # range 0.9 < 1.0 threshold
        assert _is_variable(4.0, 4.9) is False

    def test_just_above_threshold_is_variable(self):
        assert _is_variable(4.0, 5.001) is True

    def test_none_min_is_not_variable(self):
        assert _is_variable(None, 8.0) is False

    def test_none_max_is_not_variable(self):
        assert _is_variable(4.0, None) is False

    def test_both_none_is_not_variable(self):
        assert _is_variable(None, None) is False

    def test_custom_threshold(self):
        assert _is_variable(1.0, 2.0, threshold=0.5) is True
        assert _is_variable(1.0, 1.4, threshold=0.5) is False
        assert _is_variable(1.0, 1.5, threshold=0.5) is True  # exactly at threshold


# ---------------------------------------------------------------------------
# _build_star
# ---------------------------------------------------------------------------


_SIRIUS_ROW: dict[str, str] = {
    "hip": "32349",
    "hd": "48915",
    "sao": "151881",
    "proper": "Sirius",
    "ra": "6.7525",
    "dec": "-16.7161",
    "mag": "-1.46",
    "spect": "A1V",
    "dist": "2.637",
    "con": "CMa",
}


class TestBuildStar:
    def test_valid_row_produces_star(self):
        star = _build_star(_SIRIUS_ROW)
        assert star is not None
        assert star["name"] == "Sirius"
        assert star["hip"] == 32349
        assert star["hd"] == 48915
        assert star["clr"] == "#cad8ff"
        assert star["pos"] == [pytest.approx(6.7525), pytest.approx(-16.7161)]

    def test_too_dim_is_excluded(self):
        row = {**_SIRIUS_ROW, "mag": "9.0"}
        assert _build_star(row) is None

    def test_boundary_mag_included(self):
        row = {**_SIRIUS_ROW, "mag": "8.0"}
        assert _build_star(row) is not None

    def test_too_far_south_excluded(self):
        row = {**_SIRIUS_ROW, "dec": "-40.0"}
        assert _build_star(row) is None

    def test_boundary_dec_included(self):
        row = {**_SIRIUS_ROW, "dec": "-35.0"}
        assert _build_star(row) is not None

    def test_missing_mag_excluded(self):
        row = {**_SIRIUS_ROW, "mag": ""}
        assert _build_star(row) is None

    def test_missing_dec_excluded(self):
        row = {**_SIRIUS_ROW, "dec": ""}
        assert _build_star(row) is None

    def test_missing_ra_excluded(self):
        row = {**_SIRIUS_ROW, "ra": ""}
        assert _build_star(row) is None

    def test_zero_dist_excluded(self):
        # The Sun has dist=0.0 in AT-HYG and must not appear in the catalogue.
        row = {**_SIRIUS_ROW, "dist": "0.0", "proper": "Sol"}
        assert _build_star(row) is None

    def test_empty_proper_name_becomes_none(self):
        row = {**_SIRIUS_ROW, "proper": ""}
        star = _build_star(row)
        assert star is not None
        assert "name" not in star

    def test_variable_star_mag_encoded_as_range(self):
        # var_range with spread >= 1.0 → mag becomes [min, max]
        star = _build_star(_SIRIUS_ROW, var_range=(4.0, 7.5))
        assert star is not None
        assert star["mag"] == [4.0, 7.5]

    def test_variable_exactly_at_threshold(self):
        # spread == 1.0 → still encoded as [min, max] (>= is inclusive)
        star = _build_star(_SIRIUS_ROW, var_range=(5.0, 6.0))
        assert star is not None
        assert star["mag"] == [5.0, 6.0]

    def test_non_variable_mag_stays_scalar(self):
        # var_range spread 0.5 < 1.0 → mag stays a float
        star = _build_star(_SIRIUS_ROW, var_range=(5.5, 6.0))
        assert star is not None
        assert isinstance(star["mag"], float)
        assert "minmag" not in star
        assert "maxmag" not in star

    def test_no_var_range_mag_stays_scalar(self):
        # No variable data at all → mag is the CSV float
        star = _build_star(_SIRIUS_ROW)
        assert star is not None
        assert star["mag"] == pytest.approx(-1.46)

    def test_hip_zero_becomes_none(self):
        row = {**_SIRIUS_ROW, "hip": "0"}
        star = _build_star(row)
        assert star is not None
        assert "hip" not in star

    def test_constellation_absent_when_con_empty(self):
        row = {**_SIRIUS_ROW, "con": ""}
        star = _build_star(row)
        assert star is not None
        assert "const" not in star

    def test_constellation_populated_from_con(self):
        star = _build_star(_SIRIUS_ROW)
        assert star is not None
        assert star["const"] == "CMa"


    def test_dist_parsed(self):
        star = _build_star(_SIRIUS_ROW)
        assert star is not None
        assert star["dist"] == pytest.approx(2.637)
