"""Unit tests for the DSO pipeline (dso.py)."""

import csv
from pathlib import Path

from dso import (
    DsoPipeline,
    _build_dso,
    _caldwell_num,
    _catalogue_id,
    _dec_degrees,
    _is_large_diffuse,
    _messier_id,
    _ra_hours,
    _type_label,
)


def _row(**overrides: str) -> dict[str, str]:
    row = {
        "Name": "NGC0001",
        "Type": "G",
        "RA": "00:08:27.05",
        "Dec": "+27:43:03.6",
        "Const": "Peg",
        "MajAx": "2.5",
        "MinAx": "1.6",
        "PosAng": "45",
        "V-Mag": "10.4",
        "B-Mag": "11.0",
        "Hubble": "SBb",
        "Cstar V-Mag": "",
        "M": "",
        "NGC": "1",
        "IC": "",
        "Common names": "",
    }
    row.update(overrides)
    return row


_CSV_FIELDS = [
    "Name", "Type", "RA", "Dec", "Const", "MajAx", "MinAx", "PosAng",
    "B-Mag", "V-Mag", "J-Mag", "H-Mag", "K-Mag", "SurfBr", "Hubble", "Pax",
    "Pm-RA", "Pm-Dec", "RadVel", "Redshift", "Cstar U-Mag", "Cstar B-Mag",
    "Cstar V-Mag", "M", "NGC", "IC", "Cstar Names", "Identifiers",
    "Common names", "NED notes", "OpenNGC notes", "Sources",
]


def _write_openngc_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=_CSV_FIELDS, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


class TestCoordinates:
    def test_ra_hours(self):
        assert _ra_hours("12:30:00") == 12.5

    def test_dec_degrees_positive(self):
        assert _dec_degrees("+30:30:00") == 30.5

    def test_dec_degrees_negative(self):
        assert _dec_degrees("-30:30:00") == -30.5


class TestIdentifiers:
    def test_messier_id_without_padding(self):
        assert _messier_id("42") == "M42"

    def test_catalogue_prefers_messier(self):
        assert _catalogue_id(_row(M="42", NGC="1976")) == "M42"

    def test_catalogue_falls_back_to_ngc(self):
        assert _catalogue_id(_row(M="", NGC="7000")) == "NGC7000"

    def test_catalogue_strips_padding_from_ngc_column(self):
        assert _catalogue_id(_row(M="", NGC="0772")) == "NGC772"

    def test_catalogue_strips_padding_from_name_fallback(self):
        assert _catalogue_id(_row(M="", NGC="", Name="NGC0225")) == "NGC225"

    def test_caldwell_from_identifiers(self):
        assert _caldwell_num(_row(Identifiers="PGC 123,C 005,UGC 1")) == 5


class TestTypeMap:
    def test_spiral_galaxy(self):
        assert _type_label("G", "SBc") == "spiral galaxy"

    def test_elliptical_galaxy(self):
        assert _type_label("G", "E2") == "elliptical galaxy"

    def test_open_cluster(self):
        assert _type_label("OCl", "") == "open cluster"

    def test_unknown_returns_none(self):
        assert _type_label("**", "") is None


class TestDiffuseFilter:
    def test_large_diffuse_excluded(self):
        assert _is_large_diffuse("Neb", 120.0) is True

    def test_small_diffuse_kept(self):
        assert _is_large_diffuse("Neb", 30.0) is False

    def test_non_diffuse_kept(self):
        assert _is_large_diffuse("G", 120.0) is False


class TestBuildDso:
    def test_builds_galaxy_object(self):
        obj = _build_dso(_row(), note=None)
        assert obj is not None
        assert obj["ngc"] == 1
        assert "id" not in obj
        assert obj["type"] == "spiral galaxy"
        assert obj["size"] == [2.5, 1.6]

    def test_circular_size_is_scalar(self):
        obj = _build_dso(_row(MinAx="2.5"), note=None)
        assert obj is not None
        assert obj["size"] == 2.5

    def test_ngc225_name_override_is_applied(self):
        obj = _build_dso(_row(Name="NGC0225", NGC="", IC="", **{"Common names": ""}), note=None)
        assert obj is not None
        assert obj["ngc"] == 225
        assert obj["name"] == "Sailboat Cluster"

    def test_adds_note_when_present(self):
        obj = _build_dso(_row(M="42", NGC="1976"), note="Bright nebula")
        assert obj is not None
        assert obj["m"] == 42
        assert obj["ngc"] == 1976
        assert obj["note"] == "Bright nebula"

    def test_excludes_object_below_dec_limit(self):
        obj = _build_dso(_row(Dec="-50:00:00"), note=None)
        assert obj is None

    def test_messier_uncommon_type_uses_fallback(self):
        obj = _build_dso(_row(Type="Cl+N", M="42", NGC="1976"), note=None)
        assert obj is not None
        assert obj["m"] == 42
        assert obj["type"] == "emission nebula"


class TestSelectRows:
    def test_messier_plus_top_non_messier(self, tmp_path: Path):
        ngc = tmp_path / "ngc.csv"
        add = tmp_path / "add.csv"
        _write_openngc_csv(
            ngc,
            [
                {
                    **_row(),
                    "Name": "NGC1976",
                    "Type": "Neb",
                    "RA": "05:35:17.3",
                    "Dec": "-05:23:28",
                    "Const": "Ori",
                    "MajAx": "85",
                    "MinAx": "60",
                    "PosAng": "0",
                    "B-Mag": "4.0",
                    "V-Mag": "4.0",
                    "Hubble": "HII",
                    "M": "42",
                    "NGC": "1976",
                    "IC": "",
                    "Common names": "Orion Nebula",
                },
                {
                    **_row(),
                    "Name": "NGC224",
                    "Type": "G",
                    "RA": "00:42:44.3",
                    "Dec": "+41:16:09",
                    "Const": "And",
                    "MajAx": "190",
                    "MinAx": "60",
                    "PosAng": "35",
                    "B-Mag": "3.6",
                    "V-Mag": "3.4",
                    "Hubble": "Sb",
                    "M": "",
                    "NGC": "224",
                    "IC": "",
                    "Common names": "Andromeda Galaxy",
                },
            ],
        )
        _write_openngc_csv(
            add,
            [
                {
                    **_row(),
                    "Name": "IC0001",
                    "Type": "G",
                    "RA": "00:08:27.05",
                    "Dec": "+27:43:03.6",
                    "Const": "Peg",
                    "MajAx": "2.5",
                    "MinAx": "1.6",
                    "PosAng": "45",
                    "B-Mag": "10.4",
                    "V-Mag": "10.4",
                    "Hubble": "SBb",
                    "M": "",
                    "NGC": "",
                    "IC": "1",
                },
                {
                    **_row(),
                    "Name": "IC0002",
                    "Type": "G",
                    "RA": "00:09:00.00",
                    "Dec": "+20:00:00",
                    "Const": "Peg",
                    "MajAx": "2.5",
                    "MinAx": "1.6",
                    "PosAng": "45",
                    "B-Mag": "12.0",
                    "V-Mag": "12.0",
                    "Hubble": "SBb",
                    "M": "",
                    "NGC": "",
                    "IC": "2",
                },
            ],
        )

        pipeline = DsoPipeline(tmp_path, tmp_path, non_messier_num=1)
        rows = pipeline._select_rows([ngc, add], object_id=None)
        ids = [_catalogue_id(r) for r in rows]
        assert "M42" in ids
        assert "NGC224" in ids
        assert "IC1" not in ids

    def test_object_filter(self, tmp_path: Path):
        csv_path = tmp_path / "ngc.csv"
        _write_openngc_csv(
            csv_path,
            [
                {
                    **_row(),
                    "Name": "NGC224",
                    "Type": "G",
                    "RA": "00:42:44.3",
                    "Dec": "+41:16:09",
                    "Const": "And",
                    "MajAx": "190",
                    "MinAx": "60",
                    "PosAng": "35",
                    "B-Mag": "3.6",
                    "V-Mag": "3.4",
                    "Hubble": "Sb",
                    "M": "",
                    "NGC": "224",
                    "IC": "",
                    "Common names": "Andromeda Galaxy",
                },
            ],
        )
        pipeline = DsoPipeline(tmp_path, tmp_path, non_messier_num=1)
        rows = pipeline._select_rows([csv_path], object_id="NGC224")
        assert len(rows) == 1
        assert _catalogue_id(rows[0]) == "NGC224"

    def test_top_non_messier_filters_ineligible_before_cap(self, tmp_path: Path):
        csv_path = tmp_path / "ngc.csv"
        _write_openngc_csv(
            csv_path,
            [
                {
                    **_row(),
                    "Name": "NGC_BRIGHT_BADTYPE",
                    "Type": "**",
                    "RA": "00:10:00",
                    "Dec": "+10:00:00",
                    "V-Mag": "1.0",
                    "M": "",
                    "NGC": "9001",
                },
                {
                    **_row(),
                    "Name": "NGC_BRIGHT_SOUTH",
                    "Type": "G",
                    "Hubble": "Sb",
                    "RA": "00:20:00",
                    "Dec": "-50:00:00",
                    "V-Mag": "1.5",
                    "M": "",
                    "NGC": "9002",
                },
                {
                    **_row(),
                    "Name": "NGC_OK",
                    "Type": "G",
                    "Hubble": "Sb",
                    "RA": "00:30:00",
                    "Dec": "+20:00:00",
                    "V-Mag": "6.0",
                    "M": "",
                    "NGC": "9003",
                },
            ],
        )
        pipeline = DsoPipeline(tmp_path, tmp_path, non_messier_num=1)
        rows = pipeline._top_non_messier(pipeline._read_rows([csv_path]))
        assert len(rows) == 1
        assert _catalogue_id(rows[0]) == "NGC9003"
