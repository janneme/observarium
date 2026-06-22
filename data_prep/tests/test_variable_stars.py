"""Unit tests for the variable star pipeline (variable_stars.py)."""

import csv
from pathlib import Path

from variable_stars import VariableStarPipeline, _gcvs_simbad_id, _norm_varname

# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


class TestNormVarname:
    def test_collapses_internal_spaces(self):
        assert _norm_varname("alf   Ori") == "alf Ori"

    def test_strips_leading_trailing(self):
        assert _norm_varname("  bet Per  ") == "bet Per"

    def test_already_normalised(self):
        assert _norm_varname("omi Cet") == "omi Cet"


class TestGcvsSimbadId:
    def test_adds_prefix(self):
        assert _gcvs_simbad_id("alf Ori") == "V* alf Ori"

    def test_collapses_spaces_in_name(self):
        assert _gcvs_simbad_id("bet   Per") == "V* bet Per"

    def test_non_greek_variable(self):
        assert _gcvs_simbad_id("V0603 Aql") == "V* V0603 Aql"


# ---------------------------------------------------------------------------
# csv_path
# ---------------------------------------------------------------------------


class TestCsvPath:
    def test_default_max_mag(self, tmp_path: Path):
        assert VariableStarPipeline(tmp_path).csv_path().name == "variable_stars_m4.csv"

    def test_custom_max_mag(self, tmp_path: Path):
        name = VariableStarPipeline(tmp_path, max_mag=5.5).csv_path().name
        assert name == "variable_stars_m5.5.csv"


# ---------------------------------------------------------------------------
# _merge
# ---------------------------------------------------------------------------


class TestMerge:
    def _pipeline(self, tmp_path: Path) -> VariableStarPipeline:
        return VariableStarPipeline(tmp_path, max_mag=3.0)

    def test_matched_entry_returned(self, tmp_path: Path):
        gcvs = [{"var_name": "alf Ori", "mag_max": 0.0, "min1": 1.3}]
        xmatch = {"V* alf Ori": "HIP 27989"}
        result = self._pipeline(tmp_path)._merge(gcvs, xmatch)
        assert result == [(27989, 0.0, 1.3, "", "")]

    def test_no_hip_match_skipped(self, tmp_path: Path):
        gcvs = [{"var_name": "alf Ori", "mag_max": 0.0, "min1": 1.3}]
        result = self._pipeline(tmp_path)._merge(gcvs, {})
        assert result == []

    def test_normalises_reversed_order(self, tmp_path: Path):
        # When Min1 < magMax, GCVS is storing amplitude, not faint-end mag —
        # the entry must be skipped entirely.
        gcvs = [{"var_name": "bet Per", "mag_max": 3.39, "min1": 2.12}]
        xmatch = {"V* bet Per": "HIP 14576"}
        result = self._pipeline(tmp_path)._merge(gcvs, xmatch)
        assert result == []

    def test_amplitude_notation_entry_skipped(self, tmp_path: Path):
        # Denebola-style: magMax=2.14, Min1=0.03 (Min1 is the amplitude)
        gcvs = [{"var_name": "bet Leo", "mag_max": 2.14, "min1": 0.03}]
        xmatch = {"V* bet Leo": "HIP 57632"}
        assert self._pipeline(tmp_path)._merge(gcvs, xmatch) == []

    def test_result_sorted_by_hip(self, tmp_path: Path):
        gcvs = [
            {"var_name": "bet Per", "mag_max": 2.12, "min1": 3.39},
            {"var_name": "alf Ori", "mag_max": 0.0, "min1": 1.3},
        ]
        xmatch = {"V* bet Per": "HIP 14576", "V* alf Ori": "HIP 27989"}
        result = self._pipeline(tmp_path)._merge(gcvs, xmatch)
        assert [r[0] for r in result] == [14576, 27989]

    def test_invalid_hip_number_skipped(self, tmp_path: Path):
        gcvs = [{"var_name": "alf Ori", "mag_max": 0.0, "min1": 1.3}]
        xmatch = {"V* alf Ori": "HIP abc"}
        result = self._pipeline(tmp_path)._merge(gcvs, xmatch)
        assert result == []


# ---------------------------------------------------------------------------
# load_index
# ---------------------------------------------------------------------------


def _write_csv(tmp_path: Path, rows: list[dict], max_mag: float = 4.0) -> Path:
    path = tmp_path / f"variable_stars_m{max_mag:g}.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["hip", "min_mag", "max_mag", "var_type", "period"])
        writer.writeheader()
        writer.writerows(rows)
    return path


class TestLoadIndex:
    def test_loads_single_entry(self, tmp_path: Path):
        _write_csv(tmp_path, [{"hip": 27989, "min_mag": 0.0, "max_mag": 1.3}])
        assert VariableStarPipeline(tmp_path).load_index() == {27989: (0.0, 1.3, None, None)}

    def test_loads_multiple_entries(self, tmp_path: Path):
        _write_csv(tmp_path, [
            {"hip": 10826, "min_mag": 2.0, "max_mag": 10.1},
            {"hip": 14576, "min_mag": 2.12, "max_mag": 3.4},
        ])
        index = VariableStarPipeline(tmp_path).load_index()
        assert len(index) == 2
        assert index[14576] == (2.12, 3.4, None, None)

    def test_missing_csv_returns_empty_dict(self, tmp_path: Path):
        assert not VariableStarPipeline(tmp_path).load_index()

    def test_respects_max_mag_in_filename(self, tmp_path: Path):
        _write_csv(tmp_path, [{"hip": 27989, "min_mag": 0.0, "max_mag": 1.3}], max_mag=4.0)
        assert not VariableStarPipeline(tmp_path, max_mag=6.0).load_index()
        assert VariableStarPipeline(tmp_path, max_mag=4.0).load_index() == {
            27989: (0.0, 1.3, None, None)
        }
