"""Unit tests for moon feature pipeline (moon_features.py)."""

import json
from pathlib import Path

from moon_features import MoonFeaturePipeline


def test_moon_feature_pipeline_filters_and_writes(tmp_path: Path):
    sources = tmp_path / "sources"
    outdir = tmp_path / "output"
    sources.mkdir()
    csv_path = sources / "moon_features.csv"
    csv_path.write_text(
        "target,feature_type,name,lat,lon,diam_km\n"
        "Moon,Crater,Tycho,-43.31,-11.36,85\n"
        "Moon,Mare,Mare Tranquillitatis,8.5,31.4,873\n"
        "Mars,Crater,Fake,0,0,1\n"
        "Moon,Unknown,Skip,0,0,1\n",
        encoding="utf-8",
    )

    pipeline = MoonFeaturePipeline(sources, outdir)
    output = pipeline.run()
    data = json.loads(output.read_text(encoding="utf-8"))

    names = {item["name"] for item in data}
    assert names == {"Tycho", "Mare Tranquillitatis"}
    assert all(item["type"] in {"Crater", "Mare"} for item in data)
