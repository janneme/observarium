"""Unit tests for gaia.py — Gaia DR3 TAP downloader and star record builder."""

import gzip
import io
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

from gaia import (
    _SELECTED_COLUMNS,
    _adql_query,
    color_idx_from_bp_rp,
    load_gaia_stars,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PALETTE = [
    "#92b5ff",  # 0 — O
    "#b2c5ff",  # 1 — B
    "#cad8ff",  # 2 — A
    "#f8f7ff",  # 3 — F
    "#fff4e8",  # 4 — G
    "#ffd2a1",  # 5 — K
    "#ff8f6b",  # 6 — M
    "#ffffff",  # 7 — default
]


def _make_csv_gz(rows: list[dict[str, str]]) -> bytes:
    """Build gzip-compressed CSV bytes from a list of row dicts."""
    headers = list(rows[0].keys()) if rows else [
        "source_id", "ra", "dec", "phot_g_mean_mag", "bp_rp"
    ]
    buf = io.StringIO()
    buf.write(",".join(headers) + "\n")
    for row in rows:
        buf.write(",".join(row.get(h, "") for h in headers) + "\n")
    out = io.BytesIO()
    with gzip.GzipFile(fileobj=out, mode="wb") as gz:
        gz.write(buf.getvalue().encode("utf-8"))
    return out.getvalue()


def _write_csv_gz(tmp_path: Path, rows: list[dict[str, str]]) -> Path:
    p = tmp_path / "gaia_test.csv.gz"
    p.write_bytes(_make_csv_gz(rows))
    return p


# ---------------------------------------------------------------------------
# color_idx_from_bp_rp
# ---------------------------------------------------------------------------


class TestColorIdxFromBpRp:
    def test_none_returns_default(self):
        assert color_idx_from_bp_rp(None) == 7

    def test_nan_returns_default(self):
        assert color_idx_from_bp_rp(float("nan")) == 7

    def test_o_type(self):
        assert color_idx_from_bp_rp(-0.20) == 0

    def test_b_type(self):
        assert color_idx_from_bp_rp(0.10) == 1

    def test_a_type(self):
        assert color_idx_from_bp_rp(0.30) == 2

    def test_f_type(self):
        assert color_idx_from_bp_rp(0.60) == 3

    def test_g_type(self):
        assert color_idx_from_bp_rp(0.90) == 4

    def test_k_type(self):
        assert color_idx_from_bp_rp(1.50) == 5

    def test_m_type(self):
        assert color_idx_from_bp_rp(2.00) == 6

    def test_exactly_at_threshold_goes_to_next_bin(self):
        # bp_rp = -0.10 is NOT < -0.10, so falls through to next bin (B = 1)
        assert color_idx_from_bp_rp(-0.10) == 1

    def test_just_below_threshold_is_current_bin(self):
        assert color_idx_from_bp_rp(-0.101) == 0

    def test_return_is_valid_palette_index(self):
        for val in [-0.5, 0.0, 0.5, 1.0, 1.5, 2.0, None]:
            idx = color_idx_from_bp_rp(val)
            assert 0 <= idx <= 7


# ---------------------------------------------------------------------------
# _adql_query
# ---------------------------------------------------------------------------


class TestAdqlQuery:
    def test_contains_select_columns(self):
        q = _adql_query(13.0, -35.0, 11.5)
        for col in _SELECTED_COLUMNS:
            assert col in q, f"Expected column '{col}' in query"

    def test_does_not_reference_tycho2_source_id(self):
        # tycho2_source_id is NOT a column in gaiadr3.gaia_source;
        # it lives in the separate gaiadr3.tycho2tdsc_merge table.
        q = _adql_query(13.0, -35.0, 11.5)
        assert "tycho2_source_id" not in q

    def test_max_mag_bound_in_query(self):
        q = _adql_query(14.0, -35.0, 11.5)
        assert "14.0" in q

    def test_min_mag_bound_in_query(self):
        q = _adql_query(13.0, -35.0, 11.5)
        assert "11.5" in q

    def test_min_dec_bound_in_query(self):
        q = _adql_query(13.0, -40.0, 11.5)
        assert "-40.0" in q

    def test_references_correct_table(self):
        q = _adql_query(13.0, -35.0, 11.5)
        assert "gaiadr3.gaia_source" in q

    def test_only_uses_known_columns(self):
        q = _adql_query(13.0, -35.0, 11.5)
        # Every column reference in SELECT must be from the known-valid set.
        select_part = q.split("FROM", maxsplit=1)[0]
        # Strip "SELECT " prefix and split by comma
        col_names = [c.strip() for c in select_part.replace("SELECT", "").split(",")]
        for col in col_names:
            assert col in _SELECTED_COLUMNS, (
                f"Column '{col}' not in known schema columns {_SELECTED_COLUMNS}"
            )


# ---------------------------------------------------------------------------
# load_gaia_stars
# ---------------------------------------------------------------------------


class TestLoadGaiaStars:
    def test_basic_row_parsed(self, tmp_path):
        rows = [{"source_id": "1", "ra": "120.0", "dec": "10.0",
                 "phot_g_mean_mag": "12.5", "bp_rp": "0.8"}]
        p = _write_csv_gz(tmp_path, rows)
        stars = load_gaia_stars(p, 13.0, -35.0, _PALETTE)
        assert len(stars) == 1
        s = stars[0]
        assert s["mag"] == 12.5
        assert s["clr"] in _PALETTE

    def test_ra_converted_to_hours(self, tmp_path):
        rows = [{"source_id": "1", "ra": "90.0", "dec": "0.0",
                 "phot_g_mean_mag": "12.0", "bp_rp": "0.5"}]
        p = _write_csv_gz(tmp_path, rows)
        stars = load_gaia_stars(p, 13.0, -35.0, _PALETTE)
        assert stars[0]["pos"][0] == pytest.approx(6.0)  # 90 / 15 = 6 h

    def test_dec_stored_as_degrees(self, tmp_path):
        rows = [{"source_id": "1", "ra": "0.0", "dec": "45.0",
                 "phot_g_mean_mag": "12.0", "bp_rp": "0.5"}]
        p = _write_csv_gz(tmp_path, rows)
        stars = load_gaia_stars(p, 13.0, -35.0, _PALETTE)
        assert stars[0]["pos"][1] == pytest.approx(45.0)

    def test_star_above_max_mag_excluded(self, tmp_path):
        rows = [{"source_id": "1", "ra": "0.0", "dec": "0.0",
                 "phot_g_mean_mag": "13.5", "bp_rp": "0.5"}]
        p = _write_csv_gz(tmp_path, rows)
        stars = load_gaia_stars(p, 13.0, -35.0, _PALETTE)
        assert not stars

    def test_star_below_min_dec_excluded(self, tmp_path):
        rows = [{"source_id": "1", "ra": "0.0", "dec": "-50.0",
                 "phot_g_mean_mag": "12.0", "bp_rp": "0.5"}]
        p = _write_csv_gz(tmp_path, rows)
        stars = load_gaia_stars(p, 13.0, -35.0, _PALETTE)
        assert not stars

    def test_missing_bp_rp_gets_default_colour(self, tmp_path):
        rows = [{"source_id": "1", "ra": "0.0", "dec": "0.0",
                 "phot_g_mean_mag": "12.0", "bp_rp": ""}]
        p = _write_csv_gz(tmp_path, rows)
        stars = load_gaia_stars(p, 13.0, -35.0, _PALETTE)
        assert stars[0]["clr"] == _PALETTE[7]  # default colour

    def test_invalid_row_skipped(self, tmp_path):
        rows = [
            {"source_id": "1", "ra": "bad", "dec": "0.0",
             "phot_g_mean_mag": "12.0", "bp_rp": ""},
            {"source_id": "2", "ra": "10.0", "dec": "0.0",
             "phot_g_mean_mag": "12.0", "bp_rp": ""},
        ]
        p = _write_csv_gz(tmp_path, rows)
        stars = load_gaia_stars(p, 13.0, -35.0, _PALETTE)
        assert len(stars) == 1  # only the second row survives

    def test_mag_rounded_to_3dp(self, tmp_path):
        rows = [{"source_id": "1", "ra": "0.0", "dec": "0.0",
                 "phot_g_mean_mag": "12.123456", "bp_rp": "0.5"}]
        p = _write_csv_gz(tmp_path, rows)
        stars = load_gaia_stars(p, 13.0, -35.0, _PALETTE)
        assert stars[0]["mag"] == 12.123

    def test_g_type_colour(self, tmp_path):
        rows = [{"source_id": "1", "ra": "0.0", "dec": "0.0",
                 "phot_g_mean_mag": "12.0", "bp_rp": "0.90"}]
        p = _write_csv_gz(tmp_path, rows)
        stars = load_gaia_stars(p, 13.0, -35.0, _PALETTE)
        assert stars[0]["clr"] == _PALETTE[4]  # G-type yellow

    def test_multiple_rows_all_valid(self, tmp_path):
        rows = [
            {"source_id": str(i), "ra": str(i * 10.0), "dec": "0.0",
             "phot_g_mean_mag": "12.0", "bp_rp": "0.5"}
            for i in range(5)
        ]
        p = _write_csv_gz(tmp_path, rows)
        stars = load_gaia_stars(p, 13.0, -35.0, _PALETTE)
        assert len(stars) == 5


# ---------------------------------------------------------------------------
# Network smoke test — validates the ADQL against the live Gaia TAP service.
# Run with: uv run pytest -m network tests/test_gaia.py
# ---------------------------------------------------------------------------


@pytest.mark.network
def test_adql_accepted_by_gaia_tap():
    """Submit a LIMIT 5 query to verify the ADQL column names are valid."""
    base_query = _adql_query(13.0, -35.0, 12.9)
    limited = base_query.replace("SELECT ", "SELECT TOP 5 ", 1)
    body = urllib.parse.urlencode(
        {
            "REQUEST": "doQuery",
            "LANG": "ADQL",
            "QUERY": limited,
            "FORMAT": "csv",
            "PHASE": "RUN",
        }
    ).encode("ascii")
    req = urllib.request.Request(
        "https://gea.esac.esa.int/tap-server/tap/async",
        data=body,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
            job_url = resp.geturl().rstrip("/")
    except (urllib.error.URLError, TimeoutError, ConnectionResetError) as exc:
        pytest.skip(f"Gaia TAP unavailable: {exc}")

    for _ in range(30):
        try:
            with urllib.request.urlopen(f"{job_url}/phase", timeout=15) as r:  # noqa: S310
                phase = r.read().decode("ascii").strip()
        except (urllib.error.URLError, TimeoutError, ConnectionResetError) as exc:
            pytest.skip(f"Gaia TAP polling failed: {exc}")
        if phase == "COMPLETED":
            return
        if phase in ("ERROR", "ABORTED", "UNKNOWN"):
            with urllib.request.urlopen(f"{job_url}/error", timeout=15) as r:  # noqa: S310
                detail = r.read().decode("utf-8", errors="replace").strip()
            pytest.fail(f"Gaia TAP job phase={phase}: {detail}")
        time.sleep(5)
    pytest.fail("Gaia TAP smoke-test timed out after 150s")
