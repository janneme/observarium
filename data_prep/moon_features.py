"""Moon feature pipeline: USGS/IAU Gazetteer KMZ -> moon_features.json."""

# pylint: disable=duplicate-code

import json
import math
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import shapefile

from config import (
    LROC_MARE_FILENAME,
    LROC_MARE_URL,
    MEAN_MOON_DISTANCE_KM,
    MIN_MOON_ITEM_SIZE,
    MOON_AREA_TYPES,
    MOON_CIRCULAR_TOLERANCE,
    MOON_FEATURE_TYPES,
    MOON_FEATURES_FILENAME,
    MOON_FEATURES_URL,
    MOON_OUTLINE_MAX_POINTS,
)
from downloader import Downloader

Point = tuple[float, float]


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


def _delta_lon(lon: float, center_lon: float) -> float:
    """Return the shortest signed longitude offset from center_lon to lon, in (-180, 180]."""
    return (lon - center_lon + 180.0) % 360.0 - 180.0


def _perpendicular_dist(p: Point, a: Point, b: Point) -> float:
    """Return the distance from point p to the line segment a-b."""
    if a == b:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    num = abs((b[0] - a[0]) * (a[1] - p[1]) - (a[0] - p[0]) * (b[1] - a[1]))
    den = math.hypot(b[0] - a[0], b[1] - a[1])
    return num / den


def _rdp_simplify(points: list[Point], epsilon: float) -> list[Point]:
    """Ramer-Douglas-Peucker polyline simplification (iterative, stack-based).

    A recursive implementation risks Python's default recursion limit on the
    largest LROC rings (tens of thousands of points), so this uses an
    explicit stack instead.
    """
    if len(points) < 3:
        return list(points)
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        start, end = stack.pop()
        a, b = points[start], points[end]
        max_dist = -1.0
        max_index = -1
        for i in range(start + 1, end):
            dist = _perpendicular_dist(points[i], a, b)
            if dist > max_dist:
                max_dist = dist
                max_index = i
        if max_dist > epsilon:
            keep[max_index] = True
            stack.append((start, max_index))
            stack.append((max_index, end))
    return [p for p, k in zip(points, keep, strict=True) if k]


def _simplify_to_max_points(points: list[Point], max_points: int) -> list[Point]:
    """Simplify a ring down to at most max_points, growing epsilon as needed."""
    epsilon = 0.01
    result = points
    for _ in range(20):
        result = _rdp_simplify(points, epsilon)
        if len(result) <= max_points:
            return result
        epsilon *= 1.6
    return result[:: max(1, len(result) // max_points)]


# Confirmed spelling differences between our IAU-sourced catalogue names and
# the LROC shapefile's MARE_NAME field for the same real feature (typos in
# the LROC data, verified by inspection — this is intentionally a short,
# manually-checked list rather than general fuzzy matching, which would risk
# conflating two different real features that just happen to have similar
# names, e.g. Lacus Bonitatis vs. Lacus Lenitatis).
_LROC_NAME_ALIASES: dict[str, str] = {
    "Lacus Somniorum": "Lacus Somniorium",
    "Lacus Perseverantiae": "Lacus Perseveramtiae",
}


def _largest_ring(shape_points: list[Point], parts: list[int]) -> list[Point]:
    """Return the largest ring (by vertex count) of a multi-part shape.

    LROC mare polygons are often digitized as one large outer boundary plus
    many small disconnected fragments and crater-floor holes; the vertex
    count of the outer boundary dwarfs every other ring in practice, so this
    simple heuristic reliably picks it out without needing real polygon-area
    or hole/outer classification.
    """
    bounds = [*parts, len(shape_points)]
    rings = [shape_points[bounds[i] : bounds[i + 1]] for i in range(len(bounds) - 1)]
    return max(rings, key=len)


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
        outlines = self._load_mare_outlines()
        return self._write(features, outlines)

    def _load_mare_outlines(self) -> dict[str, list[Point]]:
        """Return {feature name: simplified outline ring} from the LROC mare
        boundary shapefile, keyed by exact name match against our own
        catalogue. Real digitized outlines, not a synthetic bounding box —
        see config.py's LROC_MARE_URL for provenance.

        A name can appear multiple times in the source (e.g. a mare
        digitized as a main body plus several small disconnected patches);
        only the largest-area shape per name is used, since the schematic
        map only needs the main body.
        """
        source = self._downloader.fetch(LROC_MARE_URL, LROC_MARE_FILENAME)
        best_area: dict[str, float] = {}
        best_ring: dict[str, list[Point]] = {}
        with shapefile.Reader(str(source)) as reader:
            for shape_record in reader.iterShapeRecords():
                record = shape_record.record.as_dict()
                name = str(record.get("MARE_NAME") or "").strip()
                area = float(record.get("Area_km") or 0.0)
                if not name or area <= best_area.get(name, -1.0):
                    continue
                ring = _largest_ring(shape_record.shape.points, list(shape_record.shape.parts))
                best_area[name] = area
                best_ring[name] = ring
        for our_name, lroc_name in _LROC_NAME_ALIASES.items():
            if lroc_name in best_ring and our_name not in best_ring:
                best_ring[our_name] = best_ring[lroc_name]
        return {
            name: _simplify_to_max_points(ring, MOON_OUTLINE_MAX_POINTS)
            for name, ring in best_ring.items()
        }

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
    def _round_feature(feature: dict[str, Any], outline: list[Point] | None) -> dict[str, Any]:
        """Round Moon feature using compact circular/geom schema.

        `geom` doubles as either a synthetic 4-corner bounding box (derived
        from the Gazetteer's min/max lat/lon, as before) or — when a real
        LROC outline is available for this feature — the actual digitized
        boundary as an N-corner offset polygon. Either way it's a flat list
        of (dLon, dLat) offsets from (lat, lon); the client doesn't care
        which one it is.
        """
        out: dict[str, Any] = {
            "lat": round(float(feature["lat"]), 4),
            "lon": round(float(feature["lon"]), 4),
        }

        if outline:
            center_lat = float(feature["lat"])
            center_lon = float(feature["lon"])
            geom: list[float] = []
            for lon, lat in outline:
                geom.append(round(_delta_lon(lon, center_lon), 4))
                geom.append(round(lat - center_lat, 4))
            out["geom"] = geom
            return out

        width = float(feature["size_axes"][0])
        height = float(feature["size_axes"][1])
        max_axis = max(width, height)
        min_axis = min(width, height)
        ratio = (max_axis / min_axis) if min_axis > 0 else float("inf")

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
    def _group_features(
        features: list[dict[str, Any]], outlines: dict[str, list[Point]]
    ) -> dict[str, dict[str, Any]]:
        """Group features by lowercase type and then by feature name."""
        grouped: dict[str, dict[str, Any]] = {}
        for feature in features:
            type_key = feature["type"].lower()
            outline = outlines.get(feature["name"]) if type_key in MOON_AREA_TYPES else None
            rounded = MoonFeaturePipeline._round_feature(feature, outline)
            grouped.setdefault(type_key, {})[feature["name"]] = rounded
        return dict(sorted(grouped.items()))

    def _write(self, features: list[dict[str, Any]], outlines: dict[str, list[Point]]) -> Path:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        out = self._output_dir / "moon_features.json"
        grouped = self._group_features(features, outlines)
        with out.open("w", encoding="utf-8") as fh:
            json.dump(grouped, fh, ensure_ascii=False, separators=(",", ":"))
        matched = sum(
            1
            for feature in features
            if feature["type"].lower() in MOON_AREA_TYPES and feature["name"] in outlines
        )
        print(f"Moon features  : {len(features):,} across {len(grouped):,} types")
        print(f"  with real LROC outlines: {matched:,}")
        print(f"Output         : {out} ({out.stat().st_size / 1_048_576:.2f} MB)")
        return out
