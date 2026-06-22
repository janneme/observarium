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


def test_load_systems_prefers_composite_slash_spect(tmp_path: Path) -> None:
    wds_tsv = tmp_path / "wds.tsv"
    content = (
        "WDS\tDisc\tComp\tDate\tsep1\tsep2\tmag1\tmag2\tNotes\tRAJ2000\tDEJ2000\tSpType\n"
        "12560+3819\tSTF1692\tAB\t2000\t19.2\t22.0\t2.85\t5.52\t\t12 56 01\t+38 19 06\tA0pSiEuHg\n"
        "12560+3819\tSTF1692\tAB\t2005\t19.2\t22.0\t2.85\t5.52\t\t"
        "12 56 01\t+38 19 06\tA0pSiEuHg/F2V\n"
    )
    wds_tsv.write_text(content)
    matcher = DoubleStarMatcher(tmp_path)
    systems = matcher._load_systems(wds_tsv, max_mag=9.0, min_sep=2.0)
    assert systems
    assert systems[0].get("spect") == "A0pSiEuHg / F2V"


def test_build_payload_includes_spectral_type() -> None:
    payload = DoubleStarMatcher._build_payload(
        {
            "wds": "12560+3819",
            "disc": "STF1692",
            "pairs": [{"comp": "AB", "mag": [2.85, 5.52]}],
            "spect": "A0pSiEuHg / F2V",
        }
    )
    assert payload["spect"] == "A0pSiEuHg / F2V"


def test_attach_enriches_single_spect_with_secondary_component(tmp_path: Path) -> None:
    wds_tsv = tmp_path / "wds.tsv"
    content = (
        "WDS\tDisc\tComp\tDate\tsep1\tsep2\tmag1\tmag2\tNotes\tRAJ2000\tDEJ2000\tSpType\n"
        "12560+3819\tSTF1692\tAB\t2000\t19.2\t22.0\t2.85\t5.52\t\t12 56 01\t+38 19 06\tA0pSiEuHg\n"
    )
    wds_tsv.write_text(content)

    matcher = DoubleStarMatcher(tmp_path)

    def fake_fetch(_url: str, filename: str) -> Path:
        if filename == "wds.tsv":
            return wds_tsv
        raise FileNotFoundError(filename)

    matcher._downloader.fetch = fake_fetch  # type: ignore[attr-defined]

    sep_deg = 20.0 / 3600.0
    stars = [
        {"pos": [12.9336, 38.3184], "hip": 63125, "mag": 2.89, "spect": "A0spe..."},
        {"pos": [12.9336, 38.3184 - sep_deg], "hip": 63121, "mag": 5.61, "spect": "F 0 V"},
    ]
    n_stars, n_pairs, _ = matcher.attach(stars, max_mag=9.0, min_sep=2.0)
    assert n_stars == 1
    assert n_pairs == 1
    assert stars[0]["dbl"][0]["spect"] == "A0pSiEuHg / F 0 V"
