"""Tests for ORB6 period parsing and integration with double-star matcher."""

from pathlib import Path

from double_stars import DoubleStarMatcher


def test_load_orb_periods(tmp_path: Path) -> None:
    orb_tsv = tmp_path / "orb6.tsv"
    orb_tsv.write_text("WDS\tP\n00000+0000\t12.34\n")
    matcher = DoubleStarMatcher(tmp_path)
    mapping = matcher._load_orb_periods(orb_tsv)
    assert mapping.get("00000+0000") == 12.34


def test_attach_merges_period(tmp_path: Path) -> None:
    # Create minimal WDS TSV with one system at RA=0h Dec=0deg
    wds_tsv = tmp_path / "wds.tsv"
    content = (
        "WDS\tDisc\tComp\tDate\tsep1\tsep2\tmag1\tmag2\tNotes\tRAJ2000\tDEJ2000\n"
        "00000+0000\t\tAB\t2000\t5.0\t\t1.0\t2.0\t\t00 00 00\t+00 00 00\n"
    )
    wds_tsv.write_text(content)

    orb_tsv = tmp_path / "orb6.tsv"
    orb_tsv.write_text("WDS\tP\n00000+0000\t33.21\n")

    matcher = DoubleStarMatcher(tmp_path)

    # Monkeypatch the downloader fetch to return our files based on filename
    def fake_fetch(url: str, filename: str) -> Path:
        if filename == "wds.tsv":
            return wds_tsv
        if filename == "orb6.tsv":
            return orb_tsv
        raise FileNotFoundError(filename)

    matcher._downloader.fetch = fake_fetch  # type: ignore[attr-defined]

    # Star positioned at (0h, 0deg) should match the WDS system
    stars = [{"pos": [0.0, 0.0], "hip": 1, "mag": 1.0}]
    n_stars, n_pairs = matcher.attach(stars, max_mag=5.0, min_sep=2.0)
    assert n_stars == 1
    assert n_pairs == 1
    assert "dbl" in stars[0]
    payload = stars[0]["dbl"][0]
    assert payload["wds"] == "00000+0000"
    assert payload["pairs"][0]["period"] == 33.21
