"""Unit tests for the dark-nebula supplement (dark_nebulae.py)."""

from pathlib import Path

from dark_nebulae import load_dark_nebulae


def _write_csv(path: Path, rows: list[str]) -> None:
    header = "id,name,ra_hours,dec_deg,size_maj,size_min,const"
    path.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")


class TestLoadDarkNebulae:
    def test_missing_file_returns_empty_list(self, tmp_path: Path):
        assert load_dark_nebulae(tmp_path) == []

    def test_builds_expected_object_shape(self, tmp_path: Path):
        _write_csv(
            tmp_path / "dark_nebulae.csv",
            ["B33,Horsehead Nebula (B33),5.683056,-2.458333,6,4,Ori"],
        )
        objects = load_dark_nebulae(tmp_path)
        assert len(objects) == 1
        obj = objects[0]
        assert obj["type"] == "dark nebula"
        assert obj["name"] == "Horsehead Nebula (B33)"
        assert obj["pos"] == [5.683056, -2.458333]
        assert obj["size"] == [6.0, 4.0]
        assert obj["const"] == "Ori"

    def test_equal_axes_collapse_to_scalar_size(self, tmp_path: Path):
        _write_csv(
            tmp_path / "dark_nebulae.csv",
            ["B87,Parrot's Head Nebula (B87),18.071667,-32.666667,30,30,Sgr"],
        )
        obj = load_dark_nebulae(tmp_path)[0]
        assert obj["size"] == 30.0

    def test_blank_minor_axis_collapses_to_scalar_size(self, tmp_path: Path):
        _write_csv(
            tmp_path / "dark_nebulae.csv",
            ["B133,Barnard 133,19.102778,-6.895833,6,,Aql"],
        )
        obj = load_dark_nebulae(tmp_path)[0]
        assert obj["size"] == 6.0

    def test_loads_all_rows(self, tmp_path: Path):
        _write_csv(
            tmp_path / "dark_nebulae.csv",
            [
                "B33,Horsehead Nebula (B33),5.683056,-2.458333,6,4,Ori",
                "B72,Snake Nebula (B72),17.394167,-23.695,37,17,Oph",
            ],
        )
        objects = load_dark_nebulae(tmp_path)
        assert len(objects) == 2
        assert {o["const"] for o in objects} == {"Ori", "Oph"}
