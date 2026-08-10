"""Unit tests for the distance-override module (distances.py)."""

from pathlib import Path

from distances import apply_distance_overrides, load_distance_overrides, parse_harris_catalog

_HARRIS_SAMPLE = """\


          CATALOG OF PARAMETERS FOR MILKY WAY GLOBULAR CLUSTERS:
                           THE DATABASE


   ID        Name           RA   (2000)   DEC         L       B     R_Sun  R_gc    X     Y     Z

 NGC 104    47 Tuc       00 24 05.67  -72 04 52.6   305.89  -44.89    4.5   7.4   1.9  -2.6  -3.1
 NGC 288                 00 52 45.24  -26 34 57.4   152.30  -89.38    8.9  12.0  -0.1   0.0  -8.9
 Whiting 1               02 02 57     -03 15 10     161.22  -60.76   30.1  34.5 -13.9   4.7 -26.3
 NGC 1904   M 79         05 24 11.09  -24 31 29.0   227.23  -29.35   12.9  18.8  -7.7  -8.3  -6.3

_________________________________________________________________________________________________


                    Part II:  Metallicity and Photometry
"""


class TestParseHarrisCatalog:
    def test_extracts_ngc_distance_in_parsecs(self, tmp_path: Path):
        path = tmp_path / "mwgc.dat"
        path.write_text(_HARRIS_SAMPLE, encoding="utf-8")
        result = parse_harris_catalog(path)
        assert result[104] == 4500.0
        assert result[288] == 8900.0
        assert result[1904] == 12900.0

    def test_skips_non_ngc_entries(self, tmp_path: Path):
        path = tmp_path / "mwgc.dat"
        path.write_text(_HARRIS_SAMPLE, encoding="utf-8")
        result = parse_harris_catalog(path)
        assert len(result) == 3  # Whiting 1 has no NGC number

    def test_stops_before_part_ii(self, tmp_path: Path):
        path = tmp_path / "mwgc.dat"
        path.write_text(_HARRIS_SAMPLE, encoding="utf-8")
        result = parse_harris_catalog(path)
        assert all(ngc in (104, 288, 1904) for ngc in result)


class TestLoadDistanceOverrides:
    def test_missing_file_returns_empty_dict(self, tmp_path: Path):
        assert not load_distance_overrides(tmp_path)

    def test_parses_id_and_quoted_name_keys(self, tmp_path: Path):
        path = tmp_path / "distances_dso.csv"
        path.write_text(
            'id,dist_pc\nM101,6624908\n"Wolf-Lundmark-Melotte,WLM Galaxy",970000\n',
            encoding="utf-8",
        )
        overrides = load_distance_overrides(tmp_path)
        assert overrides["M101"] == 6624908.0
        assert overrides["Wolf-Lundmark-Melotte,WLM Galaxy"] == 970000.0


class TestApplyDistanceOverrides:
    def test_globular_cluster_gets_harris_distance_by_ngc(self):
        objects = [{"type": "globular cluster", "ngc": 104, "mag": 4.0}]
        apply_distance_overrides(objects, {104: 4500.0}, {})
        assert objects[0]["dist"] == 4500.0

    def test_globular_cluster_without_harris_match_is_untouched(self):
        objects = [{"type": "globular cluster", "ngc": 9999, "mag": 4.0}]
        apply_distance_overrides(objects, {104: 4500.0}, {})
        assert "dist" not in objects[0]

    def test_harris_overrides_a_prior_pax_based_distance(self):
        objects = [{"type": "globular cluster", "ngc": 104, "dist": 12300.0}]
        apply_distance_overrides(objects, {104: 4500.0}, {})
        assert objects[0]["dist"] == 4500.0

    def test_catalogue_id_override_by_messier_number(self):
        objects = [{"type": "spiral galaxy", "m": 101, "ngc": 5457, "dist": 1.0}]
        apply_distance_overrides(objects, {}, {"M101": 6624908.0})
        assert objects[0]["dist"] == 6624908.0

    def test_name_fallback_override_for_objects_without_catalogue_numbers(self):
        objects = [{"type": "elliptical galaxy", "name": "Leo I"}]
        apply_distance_overrides(objects, {}, {"Leo I": 251401.0})
        assert objects[0]["dist"] == 251401.0

    def test_no_match_leaves_object_unchanged(self):
        objects = [{"type": "spiral galaxy", "ngc": 1, "dist": 42.0}]
        apply_distance_overrides(objects, {}, {"M101": 6624908.0})
        assert objects[0]["dist"] == 42.0
