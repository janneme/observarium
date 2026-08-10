"""Unit tests for constellation pipeline (constellations.py)."""

from pathlib import Path

from constellations import (
    ConstellationPipeline,
    _apply_czech_names,
    _line_pairs,
    _load_czech_names,
    _parse_edge_record,
)


class TestLinePairs:
    def test_empty_polyline(self):
        assert _line_pairs([]) == []

    def test_single_vertex(self):
        assert _line_pairs([123]) == []

    def test_polyline_to_adjacent_pairs(self):
        assert _line_pairs([1, 2, 3, 4]) == [[1, 2], [2, 3], [3, 4]]


class TestParseEdgeRecord:
    def test_parses_stellarium_edge(self):
        record = "001:002 M+ 22:52:00 +34:30:00 22:52:00 +52:30:00 AND LAC"
        parsed = _parse_edge_record(record)
        assert parsed == (
            "22:52:00",
            "+34:30:00",
            "22:52:00",
            "+52:30:00",
            "AND",
            "LAC",
        )

    def test_invalid_record_raises(self):
        try:
            _parse_edge_record("too short")
        except ValueError:
            pass
        else:  # pragma: no cover
            raise AssertionError("Expected ValueError")


class TestBuild:
    def test_build_uses_lines_names_and_boundaries(self, tmp_path: Path, monkeypatch):
        pipeline = ConstellationPipeline(tmp_path, tmp_path)

        def _fake_precess(ra_hms: str, dec_dms: str) -> tuple[float, float]:
            lookup = {
                ("00:00:00", "+00:00:00"): (0.0, 0.0),
                ("01:00:00", "+10:00:00"): (1.0, 10.0),
            }
            return lookup[(ra_hms, dec_dms)]

        monkeypatch.setattr("constellations._precess_b1875_to_j2000", _fake_precess)

        index = {
            "constellations": [
                {
                    "id": "CON modern_iau And",
                    "lines": [[1, 2, 3]],
                    "common_name": {
                        "native": "Andromeda",
                        "english": "Andromeda",
                        "byname": "Chained Maiden",
                    },
                },
                {
                    "id": "CON modern_iau Lyr",
                    "lines": [[4, 5]],
                    "common_name": {
                        "native": "Lyra",
                        "english": "Lyra",
                    },
                },
            ],
            "edges": [
                "001:002 M+ 00:00:00 +00:00:00 01:00:00 +10:00:00 AND LYR",
            ],
        }

        out = pipeline._build(index)
        assert set(out.keys()) == {"And", "Lyr"}
        assert out["And"]["name"] == "Andromeda"
        assert out["And"]["common"] == "Chained Maiden"
        assert out["And"]["lines"] == [[1, 2], [2, 3]]
        assert out["Lyr"]["lines"] == [[4, 5]]
        assert out["And"]["bounds"] == [[[0.0, 0.0], [1.0, 10.0]]]
        assert out["Lyr"]["bounds"] == [[[0.0, 0.0], [1.0, 10.0]]]


class TestLoadCzechNames:
    def test_missing_file_returns_empty_dict(self, tmp_path: Path):
        assert not _load_czech_names(tmp_path / "notes_constellations.csv")

    def test_parses_abbr_and_name(self, tmp_path: Path):
        path = tmp_path / "notes_constellations.csv"
        path.write_text("abbr,name_cs\nAnd,Andromeda\nUMa,Velká medvědice\n", encoding="utf-8")
        names = _load_czech_names(path)
        assert names == {"And": "Andromeda", "UMa": "Velká medvědice"}

    def test_skips_blank_rows(self, tmp_path: Path):
        path = tmp_path / "notes_constellations.csv"
        path.write_text("abbr,name_cs\nAnd,\n,Andromeda\n", encoding="utf-8")
        assert not _load_czech_names(path)


class TestApplyCzechNames:
    def test_merges_matched_abbrs_only(self):
        constellations = {"And": {"name": "Andromeda"}, "Lyr": {"name": "Lyra"}}
        _apply_czech_names(constellations, {"And": "Andromeda", "Vul": "Lištička"})
        assert constellations["And"]["name_cs"] == "Andromeda"
        assert "name_cs" not in constellations["Lyr"]
