"""Unit tests for double-star pipeline helpers (double_stars.py)."""

from pathlib import Path

from double_stars import (
    DoubleStarMatcher,
    _angular_distance_deg,
    _dec_degrees,
    _is_physical,
    _ra_hours,
    _sep_range,
)


def test_ra_hours_parses_space_separated():
    assert _ra_hours("12 30 00") == 12.5


def test_dec_degrees_parses_signed_space_separated():
    assert _dec_degrees("-30 30 00") == -30.5


def test_sep_range_uses_min_max_when_both_present():
    assert _sep_range(0.9, 2.4) == [0.9, 2.4]


def test_sep_range_scalar_when_single_value():
    assert _sep_range(None, 3.0) == 3.0


def test_angular_distance_zero_for_same_point():
    assert _angular_distance_deg(1.0, 20.0, 1.0, 20.0) == 0.0


def test_is_physical_decoding():
    assert _is_physical("P") is True
    assert _is_physical("O") is True   # O = orbital solution = physical pair
    assert _is_physical("NO") is True  # N = notes, O = orbit
    assert _is_physical("NS") is None  # S = spectroscopic data only, no phys/orbit flag
    assert _is_physical("") is None


def test_classify_apparent_pair(tmp_path: Path) -> None:
    sep_arcsec = 30.0
    sep_deg = sep_arcsec / 3600.0
    s1 = {
        "pos": [0.0, 0.0], "hip": 1, "mag": 3.0, "dist": 100.0,
        "dbl": [{"wds": "00000+0000", "pairs": [
            {"comp": "AB", "mag": [3.0, 4.0], "sep": sep_arcsec},
        ]}],
    }
    s2 = {"pos": [0.0, sep_deg], "hip": 2, "mag": 4.0, "dist": 1000.0}
    matcher = DoubleStarMatcher(tmp_path)
    n = matcher.classify_apparent_pairs([s1, s2], threshold_pc=0.1)
    assert n == 1
    assert s1["dbl"][0]["pairs"][0].get("vis") == "AB"


def test_classify_same_distance_not_apparent(tmp_path: Path) -> None:
    sep_arcsec = 30.0
    sep_deg = sep_arcsec / 3600.0
    s1 = {
        "pos": [0.0, 0.0], "hip": 1, "mag": 3.0, "dist": 100.0,
        "dbl": [{"wds": "00000+0000", "pairs": [
            {"comp": "AB", "mag": [3.0, 4.0], "sep": sep_arcsec},
        ]}],
    }
    s2 = {"pos": [0.0, sep_deg], "hip": 2, "mag": 4.0, "dist": 100.0}
    matcher = DoubleStarMatcher(tmp_path)
    n = matcher.classify_apparent_pairs([s1, s2], threshold_pc=0.1)
    assert n == 0
    assert "vis" not in s1["dbl"][0]["pairs"][0]


def test_classify_already_physical_not_overwritten(tmp_path: Path) -> None:
    sep_arcsec = 30.0
    sep_deg = sep_arcsec / 3600.0
    pair = {"comp": "AB", "mag": [3.0, 4.0], "sep": sep_arcsec, "phys": "AB"}
    s1 = {
        "pos": [0.0, 0.0], "hip": 1, "mag": 3.0, "dist": 100.0,
        "dbl": [{"wds": "00000+0000", "pairs": [pair]}],
    }
    s2 = {"pos": [0.0, sep_deg], "hip": 2, "mag": 4.0, "dist": 1000.0}
    matcher = DoubleStarMatcher(tmp_path)
    n = matcher.classify_apparent_pairs([s1, s2], threshold_pc=0.1)
    assert n == 0
    assert "vis" not in pair
