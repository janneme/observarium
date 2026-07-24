"""Unit tests for moon feature pipeline (moon_features.py)."""

import json
import math
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
import shapefile
from shapely.geometry import Polygon

from config import (
    LROC_MARE_FILENAME,
    MOON_CIRCLE_VERTEX_COUNT,
    MOON_FEATURE_TYPES,
    MOON_MIN_ITEM_SIZE_KM,
    MOON_RADIUS_KM,
)
from moon_features import (
    STYLE_FILLED,
    STYLE_RAISED,
    MoonFeaturePipeline,
    _circle_ring,
    _encode_layer,
    _subtract_obstacles,
    _valid_polygons,
)


def _write_fixture_kmz(kmz_path: Path) -> None:
    kml = """<?xml version="1.0" encoding="utf-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document><Folder>
<Placemark><name>Tycho</name><ExtendedData><SchemaData>
<SimpleData name="clean_name">Tycho</SimpleData>
<SimpleData name="approval">Adopted by IAU</SimpleData>
<SimpleData name="diameter">85</SimpleData>
<SimpleData name="center_lon">348.64</SimpleData>
<SimpleData name="center_lat">-43.31</SimpleData>
<SimpleData name="min_lon">346.5</SimpleData>
<SimpleData name="max_lon">350.6</SimpleData>
<SimpleData name="min_lat">-45.0</SimpleData>
<SimpleData name="max_lat">-41.2</SimpleData>
<SimpleData name="type">Crater, craters</SimpleData>
</SchemaData></ExtendedData></Placemark>
<Placemark><name>Mare Tranquillitatis</name><ExtendedData><SchemaData>
<SimpleData name="clean_name">Mare Tranquillitatis</SimpleData>
<SimpleData name="approval">Adopted by IAU</SimpleData>
<SimpleData name="diameter">873</SimpleData>
<SimpleData name="center_lon">31.4</SimpleData>
<SimpleData name="center_lat">8.5</SimpleData>
<SimpleData name="type">Mare, maria</SimpleData>
</SchemaData></ExtendedData></Placemark>
<Placemark><name>Mare Fixture Sea</name><ExtendedData><SchemaData>
<SimpleData name="clean_name">Mare Fixture Sea</SimpleData>
<SimpleData name="approval">Adopted by IAU</SimpleData>
<SimpleData name="diameter">400</SimpleData>
<SimpleData name="center_lon">50.0</SimpleData>
<SimpleData name="center_lat">20.0</SimpleData>
<SimpleData name="type">Mare, maria</SimpleData>
</SchemaData></ExtendedData></Placemark>
<Placemark><name>Skip Small</name><ExtendedData><SchemaData>
<SimpleData name="clean_name">Skip Small</SimpleData>
<SimpleData name="approval">Adopted by IAU</SimpleData>
<SimpleData name="diameter">1</SimpleData>
<SimpleData name="center_lon">10</SimpleData>
<SimpleData name="center_lat">10</SimpleData>
<SimpleData name="type">Crater, craters</SimpleData>
</SchemaData></ExtendedData></Placemark>
<Placemark><name>Skip Unapproved</name><ExtendedData><SchemaData>
<SimpleData name="clean_name">Skip Unapproved</SimpleData>
<SimpleData name="approval">Dropped</SimpleData>
<SimpleData name="diameter">500</SimpleData>
<SimpleData name="center_lon">10</SimpleData>
<SimpleData name="center_lat">10</SimpleData>
<SimpleData name="type">Mare, maria</SimpleData>
</SchemaData></ExtendedData></Placemark>
</Folder></Document></kml>"""
    with zipfile.ZipFile(kmz_path, "w") as zf:
        zf.writestr("MOON_nomenclature_center_pts.kml", kml)


def _write_fixture_mare_shapefile(zip_path: Path, tmp_path: Path) -> None:
    """Write a minimal LROC-shaped fixture shapefile, zipped like the real one.

    Only "Mare Fixture Sea" is present (not "Mare Tranquillitatis"), so tests
    can exercise both the real-outline path and the bounding-box fallback in
    the same run without a real network fetch.
    """
    shp_dir = tmp_path / "shp_build"
    shp_dir.mkdir(exist_ok=True)
    writer = shapefile.Writer(str(shp_dir / "mare"), shapeType=shapefile.POLYGON)
    writer.field("ID", "N")
    writer.field("MARE_NAME", "C")
    writer.field("Perimtr_km", "N", decimal=4)
    writer.field("Area_km", "N", decimal=4)
    # A small square around (50.0, 20.0) — offsets from the KML placemark's
    # center should come out as roughly (-1,-1),(1,-1),(1,1),(-1,1).
    writer.poly([[[49.0, 19.0], [51.0, 19.0], [51.0, 21.0], [49.0, 21.0], [49.0, 19.0]]])
    writer.record(1, "Mare Fixture Sea", 8.0, 4.0)
    # A tiny disconnected same-named patch with a much smaller area, to
    # verify the pipeline picks the larger shape rather than the last one.
    writer.poly([[[49.4, 19.4], [49.6, 19.4], [49.6, 19.6], [49.4, 19.6], [49.4, 19.4]]])
    writer.record(2, "Mare Fixture Sea", 0.8, 0.04)
    writer.close()
    with zipfile.ZipFile(zip_path, "w") as zf:
        for ext in ("shp", "shx", "dbf"):
            zf.write(shp_dir / f"mare.{ext}", arcname=f"mare.{ext}")


def test_moon_feature_pipeline_filters_and_writes(tmp_path: Path):
    sources = tmp_path / "sources"
    cache = tmp_path / "cache"
    outdir = tmp_path / "output"
    sources.mkdir()
    cache.mkdir()
    kmz_path = cache / "MOON_nomenclature_center_pts.kmz"
    _write_fixture_kmz(kmz_path)
    _write_fixture_mare_shapefile(cache / LROC_MARE_FILENAME, tmp_path)

    pipeline = MoonFeaturePipeline(sources, outdir, cache_dir=cache)
    output = pipeline.run()
    data = json.loads(output.read_text(encoding="utf-8"))

    assert set(data) == {"crater", "mare"}
    assert set(data["crater"]) == {"Tycho"}
    assert set(data["mare"]) == {"Mare Tranquillitatis", "Mare Fixture Sea"}

    # Tycho: no LROC entry (craters aren't in MOON_AREA_TYPES), min/max
    # lat/lon give an elongated (non-circular) bounding box once the
    # longitude span is corrected by cos(lat) (see
    # _compute_size_axes) -> a RAISED circle sized off the box's longer
    # axis (max_axis / 2): here the (corrected) width, 4.1 * cos(43.31deg)
    # = 2.98, is now smaller than the height (3.8), so height becomes the
    # longer axis, radius = 3.8 / 2 = 1.9.
    tycho = data["crater"]["Tycho"]
    assert tycho["lon"] == pytest.approx(-11.36, rel=0, abs=1e-4)
    assert tycho["lat"] == pytest.approx(-43.31, rel=0, abs=1e-4)
    assert "size" not in tycho
    assert len(tycho["geom"]) == 1
    assert tycho["geom"][0].startswith("S RAISED M")
    ring = _circle_ring(-43.31, -11.36, 1.9, MOON_CIRCLE_VERTEX_COUNT)
    assert tycho["geom"] == [_encode_layer(STYLE_RAISED, ring)]
    # Elongated (width 2.98deg corrected, height 3.8deg -> ratio ~1.27,
    # above MOON_CIRCULAR_TOLERANCE) -> not circular, both axes reported.
    km_per_deg = MOON_RADIUS_KM * math.pi / 180.0
    assert tycho["circular"] is False
    assert tycho["size_km"] == pytest.approx([2.98 * km_per_deg, 3.8 * km_per_deg], rel=1e-2)

    # No matching shapefile entry, and the KML gives no min/max lat/lon for
    # this placemark -> width == height (perfectly circular) -> a FILLED
    # circle at the old "size" scalar's radius (diam_deg / 2).
    mare = data["mare"]["Mare Tranquillitatis"]
    assert mare["lon"] == pytest.approx(31.4, rel=0, abs=1e-4)
    assert mare["lat"] == pytest.approx(8.5, rel=0, abs=1e-4)
    assert len(mare["geom"]) == 1
    assert mare["geom"][0].startswith("S FILLED M")
    assert mare["circular"] is True
    assert mare["size_km"][0] == pytest.approx(mare["size_km"][1], rel=1e-9)

    # Matches a shapefile entry — uses the real digitized outline (picking
    # the larger of the two same-named shapes) instead of a bounding box.
    fixture_sea = data["mare"]["Mare Fixture Sea"]
    assert fixture_sea["lon"] == pytest.approx(50.0, rel=0, abs=1e-4)
    assert fixture_sea["lat"] == pytest.approx(20.0, rel=0, abs=1e-4)
    expected_outline = [(49.0, 19.0), (51.0, 19.0), (51.0, 21.0), (49.0, 21.0), (49.0, 19.0)]
    assert fixture_sea["geom"] == [_encode_layer(STYLE_FILLED, expected_outline)]


def test_moon_feature_pipeline_honours_size_override(tmp_path: Path):
    sources = tmp_path / "sources"
    cache = tmp_path / "cache"
    outdir = tmp_path / "output"
    sources.mkdir()
    cache.mkdir()
    kmz_path = cache / "MOON_nomenclature_center_pts.kmz"
    _write_fixture_kmz(kmz_path)
    _write_fixture_mare_shapefile(cache / LROC_MARE_FILENAME, tmp_path)

    pipeline = MoonFeaturePipeline(sources, outdir, cache_dir=cache)
    output = pipeline.run(min_item_size=500.0)
    data = json.loads(output.read_text(encoding="utf-8"))

    assert set(data) == {"mare"}
    assert set(data["mare"]) == {"Mare Tranquillitatis"}


def test_compute_size_axes_ignores_near_pole_longitude_span():
    # A small crater right next to the pole can legitimately record a huge
    # min/max longitude span (every meridian converges there) — real data,
    # e.g. Peary at lat 88.6 records ~141 deg "width" for an ~75 km crater.
    # Trusting that width fed a bogus giant "circle" radius into obstacle
    # subtraction elsewhere on the map (see moon_pipeline.md).
    row = {
        "min_lat": "87.0",
        "max_lat": "89.9",
        "min_lon": "0.0",
        "max_lon": "300.0",
    }
    diam_deg = 0.0117
    width, height = MoonFeaturePipeline._compute_size_axes(row, diam_deg, 88.0)
    assert width == pytest.approx(diam_deg)
    assert height == pytest.approx(diam_deg)


def test_compute_size_axes_trusts_longitude_span_away_from_pole():
    row = {
        "min_lat": "-5.0",
        "max_lat": "5.0",
        "min_lon": "10.0",
        "max_lon": "20.0",
    }
    width, height = MoonFeaturePipeline._compute_size_axes(row, 1.0, 0.0)
    assert width == pytest.approx(10.0)
    assert height == pytest.approx(10.0)


def test_compute_size_axes_corrects_longitude_span_for_latitude():
    # A degree of longitude is only as physically wide as a degree of
    # latitude at the equator; at latitude phi it's narrower by cos(phi).
    # Real data: Schrodinger at lat -74.7 records a raw 41.1 deg longitude
    # "width" for a crater whose real angular size, matching its recorded
    # 10.4 deg height, is ~10 deg once corrected — an uncorrected width
    # wrongly reads as a >4x-too-big, wildly elongated shape.
    row = {
        "min_lat": "-79.95",
        "max_lat": "-69.51",
        "min_lon": "-20.0",
        "max_lon": "20.0",
    }
    lat = -74.73
    width, height = MoonFeaturePipeline._compute_size_axes(row, 1.0, lat)
    assert width == pytest.approx(40.0 * math.cos(math.radians(lat)))
    assert width == pytest.approx(10.53, abs=0.01)
    assert height == pytest.approx(10.44, abs=0.01)
    # Corrected, width and height are nearly equal (a near-circular crater)
    # instead of the raw ~4:1 ratio the uncorrected longitude span implied.
    assert width / height == pytest.approx(1.0, abs=0.02)


def test_subtract_obstacles_splits_ring_and_avoids_overlap():
    # A wide, thin ridge box...
    ridge = [(0.0, -1.0), (20.0, -1.0), (20.0, 1.0), (0.0, 1.0)]
    # ...bisected top-to-bottom by an obstacle spanning its full height.
    obstacle = [(8.0, -2.0), (12.0, -2.0), (12.0, 2.0), (8.0, 2.0)]
    obstacle_polys = _valid_polygons([obstacle])

    result = _subtract_obstacles(ridge, obstacle_polys)

    assert len(result) == 2
    obstacle_poly = Polygon(obstacle)
    for ring in result:
        piece = Polygon(ring)
        assert piece.is_valid
        assert piece.intersection(obstacle_poly).area == pytest.approx(0.0, abs=1e-9)
    # Both pieces should be on opposite sides of the cut.
    max_lons = sorted(max(p[0] for p in ring) for ring in result)
    min_lons = sorted(min(p[0] for p in ring) for ring in result)
    assert max_lons[0] <= 8.0 + 1e-9
    assert min_lons[1] >= 12.0 - 1e-9


def test_subtract_obstacles_no_overlap_returns_ring_unchanged():
    ridge = [(0.0, -1.0), (20.0, -1.0), (20.0, 1.0), (0.0, 1.0)]
    far_away = [(100.0, 50.0), (102.0, 50.0), (102.0, 52.0), (100.0, 52.0)]
    obstacle_polys = _valid_polygons([far_away])

    result = _subtract_obstacles(ridge, obstacle_polys)

    assert result == [ridge]


def test_subtract_obstacles_drops_holes_for_fully_enclosed_obstacle():
    # An obstacle entirely inside the ridge, touching no edge, would carve a
    # hole — the `geom` path format has no hole support (see
    # _subtract_obstacles' docstring), so this documents that the exterior
    # boundary is kept unchanged rather than silently mis-rendering.
    ridge = [(0.0, -5.0), (20.0, -5.0), (20.0, 5.0), (0.0, 5.0)]
    enclosed = [(9.0, -1.0), (11.0, -1.0), (11.0, 1.0), (9.0, 1.0)]
    obstacle_polys = _valid_polygons([enclosed])

    result = _subtract_obstacles(ridge, obstacle_polys)

    assert len(result) == 1
    # Same shape as the untouched ridge — shapely may reorder/reorient the
    # ring, so compare geometrically rather than as an exact point list.
    assert Polygon(result[0]).equals(Polygon(ridge))


def _write_fixture_kmz_with_mons(kmz_path: Path) -> None:
    """A mons/montes bounding box wide enough to be bisected by a mare and
    to also overlap a crater near one edge — exercises both obstacle
    sources _group_features feeds into mons subtraction."""
    kml = """<?xml version="1.0" encoding="utf-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document><Folder>
<Placemark><name>Montes Test</name><ExtendedData><SchemaData>
<SimpleData name="clean_name">Montes Test</SimpleData>
<SimpleData name="approval">Adopted by IAU</SimpleData>
<SimpleData name="diameter">2000</SimpleData>
<SimpleData name="center_lon">10.0</SimpleData>
<SimpleData name="center_lat">0.0</SimpleData>
<SimpleData name="min_lon">0.0</SimpleData>
<SimpleData name="max_lon">20.0</SimpleData>
<SimpleData name="min_lat">-1.0</SimpleData>
<SimpleData name="max_lat">1.0</SimpleData>
<SimpleData name="type">Mons, montes</SimpleData>
</SchemaData></ExtendedData></Placemark>
<Placemark><name>Mare Cut</name><ExtendedData><SchemaData>
<SimpleData name="clean_name">Mare Cut</SimpleData>
<SimpleData name="approval">Adopted by IAU</SimpleData>
<SimpleData name="diameter">2000</SimpleData>
<SimpleData name="center_lon">10.0</SimpleData>
<SimpleData name="center_lat">0.0</SimpleData>
<SimpleData name="min_lon">8.0</SimpleData>
<SimpleData name="max_lon">12.0</SimpleData>
<SimpleData name="min_lat">-1.5</SimpleData>
<SimpleData name="max_lat">1.5</SimpleData>
<SimpleData name="type">Mare, maria</SimpleData>
</SchemaData></ExtendedData></Placemark>
<Placemark><name>Crater Cut</name><ExtendedData><SchemaData>
<SimpleData name="clean_name">Crater Cut</SimpleData>
<SimpleData name="approval">Adopted by IAU</SimpleData>
<SimpleData name="diameter">8</SimpleData>
<SimpleData name="center_lon">2.0</SimpleData>
<SimpleData name="center_lat">1.0</SimpleData>
<SimpleData name="type">Crater, craters</SimpleData>
</SchemaData></ExtendedData></Placemark>
<Placemark><name>Vallis Test</name><ExtendedData><SchemaData>
<SimpleData name="clean_name">Vallis Test</SimpleData>
<SimpleData name="approval">Adopted by IAU</SimpleData>
<SimpleData name="diameter">1500</SimpleData>
<SimpleData name="center_lon">10.0</SimpleData>
<SimpleData name="center_lat">0.0</SimpleData>
<SimpleData name="min_lon">5.0</SimpleData>
<SimpleData name="max_lon">15.0</SimpleData>
<SimpleData name="min_lat">-0.5</SimpleData>
<SimpleData name="max_lat">0.5</SimpleData>
<SimpleData name="type">Vallis, valles</SimpleData>
</SchemaData></ExtendedData></Placemark>
</Folder></Document></kml>"""
    with zipfile.ZipFile(kmz_path, "w") as zf:
        zf.writestr("MOON_nomenclature_center_pts.kml", kml)


_MONS_FIXTURE_MARE_RING = [(8.0, -1.5), (12.0, -1.5), (12.0, 1.5), (8.0, 1.5)]


def _run_mons_fixture_pipeline(tmp_path: Path) -> dict:
    """Set up sources/cache/output dirs, write the mons/mare/vallis fixture,
    run the pipeline, and return its parsed JSON output."""
    sources = tmp_path / "sources"
    cache = tmp_path / "cache"
    outdir = tmp_path / "output"
    sources.mkdir()
    cache.mkdir()
    kmz_path = cache / "MOON_nomenclature_center_pts.kmz"
    _write_fixture_kmz_with_mons(kmz_path)
    _write_fixture_mare_shapefile(cache / LROC_MARE_FILENAME, tmp_path)

    pipeline = MoonFeaturePipeline(sources, outdir, cache_dir=cache)
    output = pipeline.run()
    return json.loads(output.read_text(encoding="utf-8"))


def test_mons_geom_split_and_trimmed_against_mare_and_crater(tmp_path: Path):
    data = _run_mons_fixture_pipeline(tmp_path)

    montes = data["mons"]["Montes Test"]
    # The mare cuts clean through the middle -> two disconnected pieces.
    assert len(montes["geom"]) == 2
    for layer in montes["geom"]:
        assert layer.startswith("S FILLED M")

    crater_diam_deg = MoonFeaturePipeline._selenographic_size_deg(8.0)  # pylint: disable=protected-access
    crater_ring = _circle_ring(1.0, 2.0, crater_diam_deg / 2.0, MOON_CIRCLE_VERTEX_COUNT)
    mare_poly = Polygon(_MONS_FIXTURE_MARE_RING)
    crater_poly = Polygon(crater_ring).buffer(0)
    for layer in montes["geom"]:
        piece_poly = Polygon(_decode_path_to_ring(layer))
        assert piece_poly.intersection(mare_poly).area == pytest.approx(0.0, abs=1e-6)
        assert piece_poly.intersection(crater_poly).area == pytest.approx(0.0, abs=1e-6)


def test_vallis_overlaps_mons_but_trimmed_against_mare(tmp_path: Path):
    # Vallis (and catena) get the same ridge-outline construction as mons —
    # FILLED style, not a crater-like RAISED circle — but ridge-like types
    # are never obstacles to each other: Vallis Test legitimately overlaps
    # Montes Test's box (a valley crossing a mountain range is real, not a
    # rendering bug), while it's still trimmed against the sea it crosses.
    data = _run_mons_fixture_pipeline(tmp_path)
    montes = data["mons"]["Montes Test"]
    vallis = data["vallis"]["Vallis Test"]

    # Vallis Test also straddles the mare (lon 5-15 vs. the mare's 8-12), so
    # it's split into two pieces the same way Montes Test was.
    assert len(vallis["geom"]) == 2
    for layer in vallis["geom"]:
        assert layer.startswith("S FILLED M")
    vallis_union = Polygon(_decode_path_to_ring(vallis["geom"][0])).union(
        Polygon(_decode_path_to_ring(vallis["geom"][1]))
    )
    montes_union = Polygon(_decode_path_to_ring(montes["geom"][0])).union(
        Polygon(_decode_path_to_ring(montes["geom"][1]))
    )
    mare_poly = Polygon(_MONS_FIXTURE_MARE_RING)
    assert vallis_union.intersection(montes_union).area > 0
    assert vallis_union.intersection(mare_poly).area == pytest.approx(0.0, abs=1e-6)


def _decode_path_to_ring(path: str) -> list[tuple[float, float]]:
    """Minimal decoder for 'S <STYLE> M<lat>,<lon> L<dlat>,<dlon> ... Z' —
    test-only mirror of moonMap.js's parseGeomLayers, returns (lon, lat)
    points to match this module's Point convention."""
    tokens = path.strip().split()
    assert tokens[0] == "S"
    points: list[tuple[float, float]] = []
    lat = lon = 0.0
    for tok in tokens[2:]:
        if tok == "Z":
            break
        cmd, rest = tok[0], tok[1:]
        a, b = (float(v) for v in rest.split(","))
        if cmd == "M":
            lat, lon = a, b
        elif cmd == "L":
            lat += a
            lon += b
        points.append((lon, lat))
    return points


def _make_placemark(
    type_str: str,
    diam_km: float,
    *,
    name: str = "Test Feature",
    lat: float = 0.0,
    lon: float = 0.0,
    min_lat: float | None = None,
    max_lat: float | None = None,
    min_lon: float | None = None,
    max_lon: float | None = None,
) -> ET.Element:
    """Build a single <Placemark> element, for tests exercising
    MoonFeaturePipeline._parse_placemark directly without a full KMZ fixture."""
    bounds = ""
    if None not in (min_lat, max_lat, min_lon, max_lon):
        bounds = (
            f'<SimpleData name="min_lat">{min_lat}</SimpleData>'
            f'<SimpleData name="max_lat">{max_lat}</SimpleData>'
            f'<SimpleData name="min_lon">{min_lon}</SimpleData>'
            f'<SimpleData name="max_lon">{max_lon}</SimpleData>'
        )
    xml = f"""<Placemark xmlns="http://www.opengis.net/kml/2.2"><name>{name}</name>
<ExtendedData><SchemaData>
<SimpleData name="clean_name">{name}</SimpleData>
<SimpleData name="approval">Adopted by IAU</SimpleData>
<SimpleData name="diameter">{diam_km}</SimpleData>
<SimpleData name="center_lon">{lon}</SimpleData>
<SimpleData name="center_lat">{lat}</SimpleData>
{bounds}
<SimpleData name="type">{type_str}</SimpleData>
</SchemaData></ExtendedData></Placemark>"""
    return ET.fromstring(xml)  # noqa: S314 -- self-authored fixture XML, not untrusted input


_KML_NS = {"kml": "http://www.opengis.net/kml/2.2"}


def test_parse_placemark_aliases_satellite_feature_to_crater():
    placemark = _make_placemark(
        "Satellite Feature",
        5.0,
        name="Cassini A",
        min_lat=16.5,
        max_lat=17.4,
        min_lon=343.0,
        max_lon=344.0,
    )
    feature = MoonFeaturePipeline._parse_placemark(  # pylint: disable=protected-access
        placemark, _KML_NS, set(MOON_FEATURE_TYPES), MOON_MIN_ITEM_SIZE_KM
    )
    assert feature is not None
    assert feature["type"] == "Crater"


def test_parse_placemark_aliases_rima_to_vallis():
    placemark = _make_placemark(
        "Rima, rimae",
        20.0,
        name="Rima Test",
        min_lat=24.5,
        max_lat=24.6,
        min_lon=10.0,
        max_lon=10.5,
    )
    feature = MoonFeaturePipeline._parse_placemark(  # pylint: disable=protected-access
        placemark, _KML_NS, set(MOON_FEATURE_TYPES), MOON_MIN_ITEM_SIZE_KM
    )
    assert feature is not None
    assert feature["type"] == "Vallis"


def test_parse_placemark_aliases_dorsum_to_mons():
    placemark = _make_placemark(
        "Dorsum, dorsa",
        30.0,
        name="Dorsum Test",
        min_lat=11.7,
        max_lat=16.5,
        min_lon=20.0,
        max_lon=21.0,
    )
    feature = MoonFeaturePipeline._parse_placemark(  # pylint: disable=protected-access
        placemark, _KML_NS, set(MOON_FEATURE_TYPES), MOON_MIN_ITEM_SIZE_KM
    )
    assert feature is not None
    assert feature["type"] == "Mons"


def test_parse_placemark_rejects_bbox_below_min_size_km():
    # No min/max bounds -> falls back to a circle sized from the
    # selenographic diameter directly, so its bounding box is ~diam_km wide.
    placemark = _make_placemark("Crater, craters", 1.5, name="Tiny Crater")
    feature = MoonFeaturePipeline._parse_placemark(  # pylint: disable=protected-access
        placemark, _KML_NS, set(MOON_FEATURE_TYPES), MOON_MIN_ITEM_SIZE_KM
    )
    assert feature is None


def test_parse_placemark_accepts_bbox_above_min_size_km():
    placemark = _make_placemark("Crater, craters", 2.5, name="Small Crater")
    feature = MoonFeaturePipeline._parse_placemark(  # pylint: disable=protected-access
        placemark, _KML_NS, set(MOON_FEATURE_TYPES), MOON_MIN_ITEM_SIZE_KM
    )
    assert feature is not None
