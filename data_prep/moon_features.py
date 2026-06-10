"""Moon feature pipeline: USGS/IAU Gazetteer KMZ -> moon_features.json."""

# pylint: disable=duplicate-code

import json
import math
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from config import (
    MEAN_MOON_DISTANCE_KM,
    MIN_MOON_ITEM_SIZE,
    MOON_CIRCULAR_TOLERANCE,
    MOON_FEATURE_TYPES,
    MOON_FEATURES_FILENAME,
    MOON_FEATURES_URL,
)
from downloader import Downloader


def _float_or_none(value: str) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _normalize_lon(lon: float) -> float:
    """Normalize longitude from [0, 360] east to [-180, 180]."""
    return lon - 360.0 if lon > 180.0 else lon


def _lon_span_deg(min_lon: float, max_lon: float) -> float:
    """Return shortest longitudinal span in degrees for [0, 360] longitudes."""
    span = (max_lon - min_lon) % 360.0
    if span > 180.0:
        span = 360.0 - span
    return span


class MoonFeaturePipeline:
    """Filter Moon features from the Gazetteer and write moon_features.json."""

    def __init__(
        self,
        sources_dir: Path,
        output_dir: Path,
        cache_dir: Path | None = None,
        debug: bool = False,
    ) -> None:
        self._sources_dir = sources_dir
        self._output_dir = output_dir
        cache = cache_dir or sources_dir
        self._downloader = Downloader(cache, debug=debug)

    @staticmethod
    def _angular_size_deg(diam_km: float) -> float:
        """Return apparent angular diameter in degrees at mean Moon distance."""
        return math.degrees(2.0 * math.atan(diam_km / (2.0 * MEAN_MOON_DISTANCE_KM)))

    def run(self, min_item_size: float | None = None) -> Path:
        """Execute full pipeline and return output path."""
        source = self._downloader.fetch(MOON_FEATURES_URL, MOON_FEATURES_FILENAME)
        features = self._process(source, min_item_size=min_item_size)
        return self._write(features)

    @staticmethod
    def _compute_size_axes(row: dict[str, str], diam_deg: float) -> tuple[float, float]:
        min_lat = _float_or_none(row.get("min_lat", ""))
        max_lat = _float_or_none(row.get("max_lat", ""))
        min_lon = _float_or_none(row.get("min_lon", ""))
        max_lon = _float_or_none(row.get("max_lon", ""))
        if None not in (min_lat, max_lat, min_lon, max_lon):
            width = _lon_span_deg(float(min_lon), float(max_lon))  # type: ignore[arg-type]
            height = abs(float(max_lat) - float(min_lat))  # type: ignore[arg-type]
            return width, height
        return diam_deg, diam_deg

    @staticmethod
    def _parse_placemark(
        placemark: Any,
        ns: dict[str, str],
        allowed: set[str],
        min_size: float,
    ) -> dict[str, Any] | None:
        row = {
            data.attrib.get("name", ""): (data.text or "").strip()
            for data in placemark.findall(".//kml:SimpleData", ns)
        }
        feature_type = row.get("type", "").split(",", 1)[0].strip()
        if feature_type not in allowed:
            return None
        if "IAU" not in row.get("approval", ""):
            return None
        name = (row.get("clean_name") or placemark.findtext("kml:name", "", ns)).strip()
        lat = _float_or_none(row.get("center_lat", ""))
        lon = _float_or_none(row.get("center_lon", ""))
        diam_km = _float_or_none(row.get("diameter", ""))
        if not name or lat is None or lon is None or diam_km is None:
            return None
        diam_deg = MoonFeaturePipeline._angular_size_deg(diam_km)
        if diam_deg < min_size:
            return None
        width, height = MoonFeaturePipeline._compute_size_axes(row, diam_deg)
        return {
            "name": name,
            "type": feature_type,
            "lat": lat,
            "lon": _normalize_lon(lon),
            "size_axes": [width, height],
        }

    def _process(
        self,
        source: Path,
        min_item_size: float | None = None,
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        allowed = set(MOON_FEATURE_TYPES)
        min_size = MIN_MOON_ITEM_SIZE if min_item_size is None else min_item_size
        with zipfile.ZipFile(source) as zf:
            kml_name = next(name for name in zf.namelist() if name.endswith(".kml"))
            # Source is a fixed USGS/IAU Gazetteer KMZ over HTTPS.
            root = ET.fromstring(zf.read(kml_name))  # noqa: S314
        ns = {"kml": "http://www.opengis.net/kml/2.2"}
        for placemark in root.findall(".//kml:Placemark", ns):
            feature = self._parse_placemark(placemark, ns, allowed, min_size)
            if feature is not None:
                out.append(feature)
        out.sort(key=lambda f: (f["type"], f["name"]))
        return out

    @staticmethod
    def _round_feature(feature: dict[str, Any]) -> dict[str, Any]:
        """Round Moon feature using compact circular/geom schema."""
        width = float(feature["size_axes"][0])
        height = float(feature["size_axes"][1])
        max_axis = max(width, height)
        min_axis = min(width, height)
        ratio = (max_axis / min_axis) if min_axis > 0 else float("inf")

        out: dict[str, Any] = {
            "lat": round(float(feature["lat"]), 4),
            "lon": round(float(feature["lon"]), 4),
        }

        if ratio <= MOON_CIRCULAR_TOLERANCE:
            out["size"] = round((width + height) / 2.0, 4)
            return out

        half_w = width / 2.0
        half_h = height / 2.0
        out["geom"] = [
            round(-half_w, 4),
            round(-half_h, 4),
            round(half_w, 4),
            round(-half_h, 4),
            round(half_w, 4),
            round(half_h, 4),
            round(-half_w, 4),
            round(half_h, 4),
        ]
        return out

    @staticmethod
    def _group_features(features: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """Group features by lowercase type and then by feature name."""
        grouped: dict[str, dict[str, Any]] = {}
        for feature in features:
            type_key = feature["type"].lower()
            rounded = MoonFeaturePipeline._round_feature(feature)
            grouped.setdefault(type_key, {})[feature["name"]] = rounded
        return dict(sorted(grouped.items()))

    def _write(self, features: list[dict[str, Any]]) -> Path:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        out = self._output_dir / "moon_features.json"
        grouped = self._group_features(features)
        with out.open("w", encoding="utf-8") as fh:
            json.dump(grouped, fh, ensure_ascii=False, separators=(",", ":"))
        print(f"Moon features  : {len(features):,} across {len(grouped):,} types")
        print(f"Output         : {out} ({out.stat().st_size / 1_048_576:.2f} MB)")
        return out
