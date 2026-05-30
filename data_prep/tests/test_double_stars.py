"""Unit tests for double-star pipeline helpers (double_stars.py)."""

from double_stars import (
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
    assert _is_physical("O") is False
    assert _is_physical("") is None
