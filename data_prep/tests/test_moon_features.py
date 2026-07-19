"""Unit tests for moon feature pipeline (moon_features.py)."""

import json
import zipfile
from pathlib import Path

import pytest
import shapefile

from config import LROC_MARE_FILENAME
from moon_features import MoonFeaturePipeline


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
<SimpleData name="diameter">10</SimpleData>
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

    tycho = data["crater"]["Tycho"]
    assert tycho["lon"] == pytest.approx(-11.36, rel=0, abs=1e-4)
    assert tycho["lat"] == pytest.approx(-43.31, rel=0, abs=1e-4)
    assert "geom" in tycho
    assert "size" not in tycho
    expected_geom = [-2.05, -1.9, 2.05, -1.9, 2.05, 1.9, -2.05, 1.9]
    assert tycho["geom"] == pytest.approx(expected_geom, rel=0, abs=1e-4)

    # No matching shapefile entry — falls back to the synthetic bounding box.
    mare = data["mare"]["Mare Tranquillitatis"]
    assert mare["lon"] == pytest.approx(31.4, rel=0, abs=1e-4)
    assert mare["lat"] == pytest.approx(8.5, rel=0, abs=1e-4)
    assert "size" in mare
    assert "geom" not in mare

    # Matches a shapefile entry — uses the real digitized outline (picking
    # the larger of the two same-named shapes) instead of a bounding box.
    fixture_sea = data["mare"]["Mare Fixture Sea"]
    assert fixture_sea["lon"] == pytest.approx(50.0, rel=0, abs=1e-4)
    assert fixture_sea["lat"] == pytest.approx(20.0, rel=0, abs=1e-4)
    assert "size" not in fixture_sea
    expected_outline_geom = [-1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, -1.0, -1.0]
    assert fixture_sea["geom"] == pytest.approx(expected_outline_geom, rel=0, abs=1e-4)


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
    output = pipeline.run(min_item_size=0.1)
    data = json.loads(output.read_text(encoding="utf-8"))

    assert set(data) == {"mare"}
    assert set(data["mare"]) == {"Mare Tranquillitatis"}
