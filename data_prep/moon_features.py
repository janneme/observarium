"""Moon feature pipeline: local CSV -> data_prep/output/moon_features.json."""

# pylint: disable=duplicate-code

import csv
import json
from pathlib import Path
from typing import Any

from config import MOON_FEATURE_TYPES, MOON_FEATURES_SOURCE_FILENAME


def _float_or_none(value: str) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


class MoonFeaturePipeline:
    """Filter moon features from a source CSV and write moon_features.json."""

    def __init__(self, sources_dir: Path, output_dir: Path) -> None:
        self._sources_dir = sources_dir
        self._output_dir = output_dir

    def run(self) -> Path:
        """Execute full pipeline and return output path."""
        source = self._sources_dir / MOON_FEATURES_SOURCE_FILENAME
        if not source.exists():
            raise FileNotFoundError(
                f"Moon feature source not found: {source}. "
                "Provide a CSV with columns: target,feature_type,name,lat,lon,diam_km"
            )
        features = self._process(source)
        return self._write(features)

    def _process(self, source: Path) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        allowed = set(MOON_FEATURE_TYPES)
        with source.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                target = (row.get("target", "") or "").strip().lower()
                feature_type = (row.get("feature_type", "") or "").strip()
                if target != "moon" or feature_type not in allowed:
                    continue
                name = (row.get("name", "") or "").strip()
                lat = _float_or_none((row.get("lat", "") or "").strip())
                lon = _float_or_none((row.get("lon", "") or "").strip())
                diam_km = _float_or_none((row.get("diam_km", "") or "").strip())
                if not name or lat is None or lon is None:
                    continue
                item: dict[str, Any] = {
                    "name": name,
                    "type": feature_type,
                    "lat": lat,
                    "lon": lon,
                }
                if diam_km is not None:
                    item["diam_km"] = diam_km
                out.append(item)
        out.sort(key=lambda f: (f["type"], f["name"]))
        return out

    def _write(self, features: list[dict[str, Any]]) -> Path:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        out = self._output_dir / "moon_features.json"
        with out.open("w", encoding="utf-8") as fh:
            json.dump(features, fh, ensure_ascii=False)
        print(f"Moon features  : {len(features):,}")
        print(f"Output         : {out} ({out.stat().st_size / 1_048_576:.2f} MB)")
        return out
