"""Unit tests for the star catalogue pipeline (stars.py)."""

from pathlib import Path

import pytest

from stars import (
    StarPipeline,
    _bayer_letter,
    _build_star,
    _is_variable,
    _load_notes,
    _parse_lum_class,
    _parse_spec_class,
    spectral_colour,
    variable_threshold,
)

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
        assert _is_variable(5.0, 8.5, threshold=1.0) is True

    def test_small_range_is_not_variable(self):
        assert _is_variable(6.0, 6.5, threshold=1.0) is False

    def test_exactly_threshold_is_variable(self):
        # range == threshold, >= is inclusive
        assert _is_variable(4.0, 5.0, threshold=1.0) is True

    def test_below_threshold_is_not_variable(self):
        # range 0.9 < 1.0 threshold
        assert _is_variable(4.0, 4.9, threshold=1.0) is False

    def test_just_above_threshold_is_variable(self):
        assert _is_variable(4.0, 5.001, threshold=1.0) is True

    def test_none_min_is_not_variable(self):
        assert _is_variable(None, 8.0, threshold=1.0) is False

    def test_none_max_is_not_variable(self):
        assert _is_variable(4.0, None, threshold=1.0) is False

    def test_both_none_is_not_variable(self):
        assert _is_variable(None, None, threshold=1.0) is False

    def test_custom_threshold(self):
        assert _is_variable(1.0, 2.0, threshold=0.5) is True
        assert _is_variable(1.0, 1.4, threshold=0.5) is False
        assert _is_variable(1.0, 1.5, threshold=0.5) is True  # exactly at threshold


# ---------------------------------------------------------------------------
# variable_threshold
# ---------------------------------------------------------------------------


class TestVariableThreshold:
    def test_at_mag_zero_equals_bright_threshold(self):
        assert variable_threshold(0.0, bright_threshold=0.7) == pytest.approx(0.7)

    def test_at_mag_ten_equals_three_times_bright_threshold(self):
        assert variable_threshold(10.0, bright_threshold=0.7) == pytest.approx(2.1)

    def test_formula_is_cubic(self):
        # T(m) = T0 * (1 + 2*(m/10)^3); at m=5: T0*(1+2*0.125) = 1.25*T0
        assert variable_threshold(5.0, bright_threshold=1.0) == pytest.approx(1.25)

    def test_brighter_than_five_is_nearly_flat(self):
        # At m=3: T0*(1+2*0.027) = 1.054*T0 — within 6% of T0
        t3 = variable_threshold(3.0, bright_threshold=1.0)
        assert t3 == pytest.approx(1.054, rel=1e-3)

    def test_default_bright_threshold(self):
        # Default BRIGHT_VARIABLE_THRESHOLD=0.7; at m=0 should equal 0.7
        assert variable_threshold(0.0) == pytest.approx(0.7)


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


# ---------------------------------------------------------------------------
# _load_notes
# ---------------------------------------------------------------------------


class TestLoadNotes:
    def test_returns_empty_dict_when_file_absent(self, tmp_path: Path):
        assert not _load_notes(tmp_path / "no_such_file.csv")

    def test_loads_hip_note_pairs(self, tmp_path: Path):
        csv_file = tmp_path / "notes_stars.csv"
        csv_file.write_text("hip,note\n32349,Brightest star\n27989,Red supergiant\n")
        notes = _load_notes(csv_file)
        assert notes == {32349: "Brightest star", 27989: "Red supergiant"}

    def test_skips_rows_with_empty_note(self, tmp_path: Path):
        csv_file = tmp_path / "notes_stars.csv"
        csv_file.write_text("hip,note\n32349,\n27989,Red supergiant\n")
        notes = _load_notes(csv_file)
        assert 32349 not in notes
        assert notes[27989] == "Red supergiant"

    def test_skips_rows_with_invalid_hip(self, tmp_path: Path):
        csv_file = tmp_path / "notes_stars.csv"
        csv_file.write_text("hip,note\nnot_a_number,Some note\n32349,Valid\n")
        notes = _load_notes(csv_file)
        assert len(notes) == 1
        assert notes[32349] == "Valid"


# ---------------------------------------------------------------------------
# _bayer_letter
# ---------------------------------------------------------------------------


class TestBayerLetter:
    def test_standard_three_letter(self):
        assert _bayer_letter("Alp") == "α"
        assert _bayer_letter("Del") == "δ"
        assert _bayer_letter("Ome") == "ω"

    def test_two_letter_abbreviations(self):
        assert _bayer_letter("Mu") == "μ"
        assert _bayer_letter("Nu") == "ν"
        assert _bayer_letter("Pi") == "π"
        assert _bayer_letter("Xi") == "ξ"

    def test_numbered_bayer_uses_superscript(self):
        assert _bayer_letter("Kap-1") == "κ¹"
        assert _bayer_letter("Bet-2") == "β²"

    def test_empty_returns_none(self):
        assert _bayer_letter("") is None

    def test_unrecognised_returns_none(self):
        assert _bayer_letter("Xyz") is None


# ---------------------------------------------------------------------------
# _parse_spec_class
# ---------------------------------------------------------------------------


class TestParseSpecClass:
    def test_b_type(self):
        assert _parse_spec_class("B7III") == "hot blue-white"

    def test_m_type(self):
        assert _parse_spec_class("M2IA") == "red"

    def test_k_type_no_lum_class(self):
        assert _parse_spec_class("K5") == "orange"

    def test_a_type_main_sequence(self):
        assert _parse_spec_class("A0V") == "white"

    def test_wolf_rayet(self):
        assert _parse_spec_class("WC7") == "Wolf-Rayet"

    def test_empty_returns_none(self):
        assert _parse_spec_class("") is None

    def test_unrecognised_returns_none(self):
        assert _parse_spec_class("XYZ") is None


# ---------------------------------------------------------------------------
# _parse_lum_class
# ---------------------------------------------------------------------------


class TestParseLumClass:
    def test_supergiant_ia(self):
        assert _parse_lum_class("M2IA") == "luminous supergiant"

    def test_supergiant_ib(self):
        assert _parse_lum_class("F5IB") == "supergiant"

    def test_giant(self):
        assert _parse_lum_class("B7III") == "giant"

    def test_main_sequence(self):
        assert _parse_lum_class("A0V") == "main-sequence star"

    def test_subgiant(self):
        assert _parse_lum_class("G2IV") == "subgiant"

    def test_composite_spectral_type_uses_first_class(self):
        # F5IB-G1IB: first component is "IB" → supergiant
        assert _parse_lum_class("F5IB-G1IB") == "supergiant"

    def test_no_lum_class_returns_none(self):
        assert _parse_lum_class("K5") is None

    def test_empty_returns_none(self):
        assert _parse_lum_class("") is None


# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# StarPipeline._cap_luminosity_notes
# ---------------------------------------------------------------------------


def _lsun_star(lsun: int) -> dict:
    phrase = f"~{lsun:,}\u00d7 the Sun's luminosity"
    return {"note": f"Type desc; {phrase}", "_lsun": float(lsun), "_lsun_phrase": phrase}


class TestCapLuminosityNotes:
    def test_top_five_keep_luminosity_phrase(self):
        stars = [_lsun_star(lsun) for lsun in [100_000, 50_000, 20_000, 10_000, 5_000]]
        stars.append({"note": "No lsun note"})
        StarPipeline._cap_luminosity_notes(stars)
        for s in stars[:5]:
            assert "\u00d7 the Sun's luminosity" in s["note"]

    def test_sixth_loses_luminosity_phrase(self):
        stars = [_lsun_star(lsun) for lsun in [100_000, 50_000, 20_000, 10_000, 5_000, 1_000]]
        StarPipeline._cap_luminosity_notes(stars)
        without = [s for s in stars if "\u00d7 the Sun's luminosity" not in s["note"]]
        assert len(without) == 1
        assert "Type desc" in without[0]["note"]

    def test_temp_fields_removed_after_cap(self):
        stars = [_lsun_star(lsun) for lsun in [100_000, 50_000, 20_000, 10_000, 5_000, 1_000]]
        StarPipeline._cap_luminosity_notes(stars)
        for s in stars:
            assert "_lsun" not in s
            assert "_lsun_phrase" not in s
