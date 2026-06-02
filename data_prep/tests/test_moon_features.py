"""Unit tests for moon feature pipeline (moon_features.py)."""

import json
from pathlib import Path
import zipfile

import pytest

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


def test_moon_feature_pipeline_filters_and_writes(tmp_path: Path):
    sources = tmp_path / "sources"
    cache = tmp_path / "cache"
    outdir = tmp_path / "output"
    sources.mkdir()
    cache.mkdir()
    kmz_path = cache / "MOON_nomenclature_center_pts.kmz"
    _write_fixture_kmz(kmz_path)

    pipeline = MoonFeaturePipeline(sources, outdir, cache_dir=cache)
    output = pipeline.run()
    data = json.loads(output.read_text(encoding="utf-8"))

    assert set(data) == {"crater", "mare"}

    tycho = data["crater"]["Tycho"]
    assert tycho["lon"] == pytest.approx(-11.36, rel=0, abs=1e-4)
    assert tycho["lat"] == pytest.approx(-43.31, rel=0, abs=1e-4)
    assert "geom" in tycho
    assert "size" not in tycho
    assert tycho["geom"] == pytest.approx([-2.05, -1.9, 2.05, -1.9, 2.05, 1.9, -2.05, 1.9], rel=0, abs=1e-4)

    mare = data["mare"]["Mare Tranquillitatis"]
    assert mare["lon"] == pytest.approx(31.4, rel=0, abs=1e-4)
    assert mare["lat"] == pytest.approx(8.5, rel=0, abs=1e-4)
    assert "size" in mare
    assert "geom" not in mare


def test_moon_feature_pipeline_honours_size_override(tmp_path: Path):
    sources = tmp_path / "sources"
    cache = tmp_path / "cache"
    outdir = tmp_path / "output"
    sources.mkdir()
    cache.mkdir()
    kmz_path = cache / "MOON_nomenclature_center_pts.kmz"
    _write_fixture_kmz(kmz_path)

    pipeline = MoonFeaturePipeline(sources, outdir, cache_dir=cache)
    output = pipeline.run(min_item_size=0.1)
    data = json.loads(output.read_text(encoding="utf-8"))

    assert set(data) == {"mare"}
    assert set(data["mare"]) == {"Mare Tranquillitatis"}
