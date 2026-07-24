"""Moon feature pipeline: USGS/IAU Gazetteer KMZ -> moon_features.json."""

# pylint: disable=duplicate-code

import json
import math
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import shapefile
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union

from config import (
    LROC_MARE_FILENAME,
    LROC_MARE_URL,
    MOON_AREA_TYPES,
    MOON_CIRCLE_VERTEX_COUNT,
    MOON_CIRCULAR_TOLERANCE,
    MOON_FEATURE_TYPES,
    MOON_FEATURES_FILENAME,
    MOON_FEATURES_URL,
    MOON_MIN_ITEM_SIZE_KM,
    MOON_OUTLINE_MAX_POINTS,
    MOON_POLAR_LAT_GUARD_DEG,
    MOON_RADIUS_KM,
    MOON_RIDGE_CORNER_RADIUS_RATIO,
    MOON_RIDGE_CORNER_SEGMENTS,
    MOON_TYPE_ALIASES,
)
from downloader import Downloader

Point = tuple[float, float]

#: `geom` layer style tags — see moon_pipeline.md. FILLED: solid area,
#: two-pass edge+inset border (mare/oceanus/palus/lacus/mons/catena/vallis).
#: RAISED: crater-style rim treatment (crater only).
STYLE_FILLED = "FILLED"
STYLE_RAISED = "RAISED"

#: Linear/elongated terrain features that get the same ridge-outline
#: construction and obstacle subtraction as mons/montes (see
#: _group_features) — catena (crater chains) and vallis (valleys/rilles)
#: are real linear features, not circular impacts, so a crater-style RAISED
#: circle misrepresents them just as badly as it would a mountain range.
MOON_RIDGE_LIKE_TYPES = frozenset({"mons", "catena", "vallis"})


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


def _circle_ring(lat: float, lon: float, radius_deg: float, n_points: int) -> list[Point]:
    """Sample a circle of the given angular radius into n_points (lon, lat) offsets."""
    return [
        (
            lon + radius_deg * math.cos(2.0 * math.pi * i / n_points),
            lat + radius_deg * math.sin(2.0 * math.pi * i / n_points),
        )
        for i in range(n_points)
    ]


def _ridge_corner_params(
    width: float, height: float, corner_ratio: float
) -> tuple[float, float, list[tuple[float, float, float]]]:
    """Return (rx, ry, corners) — the rounded-corner ellipse radii and each
    corner's (dx, dy, start_angle_deg) placement relative to the box centre.

    Each corner entry is a quarter-ellipse arc (NE/NW/SW/SE); consecutive
    corners' arc endpoints already share an axis, so no explicit edge points
    are needed — straight connectors between them form the flat sides.
    """
    half_w = width / 2.0
    half_h = height / 2.0
    ratio = max(0.0, min(1.0, corner_ratio))
    rx = half_w * ratio
    ry = half_h * ratio
    cx = half_w - rx
    cy = half_h - ry
    corners = [(cx, cy, 0.0), (-cx, cy, 90.0), (-cx, -cy, 180.0), (cx, -cy, 270.0)]
    return rx, ry, corners


def _ridge_corner_arc_points(
    lat: float, lon: float, ox: float, oy: float, start: float, rx: float, ry: float, segments: int
) -> list[Point]:
    """Sample one quarter-ellipse corner arc into (lon, lat) points."""
    points: list[Point] = []
    for i in range(segments + 1):
        rad = math.radians(start + 90.0 * i / segments)
        points.append((lon + ox + rx * math.cos(rad), lat + oy + ry * math.sin(rad)))
    return points


def _ridge_outline(
    lat: float,
    lon: float,
    width: float,
    height: float,
    corner_ratio: float,
    segments: int,
) -> list[Point]:
    """Round a mons/montes bounding box into a ridge-like outline.

    No real digitized outline exists publicly for lunar mountain ranges (see
    MOON_RIDGE_CORNER_RADIUS_RATIO in config.py) — a sharp-cornered quad
    reads as an obviously synthetic rectangle, so this rounds the corners
    (by an amount relative to the box's own size) as a better visual
    approximation of a ridge/massif footprint without claiming precision the
    source data doesn't have. Ported from the client's former ridgeOutline().
    """
    rx, ry, corners = _ridge_corner_params(width, height, corner_ratio)
    points: list[Point] = []
    for ox, oy, start in corners:
        points.extend(_ridge_corner_arc_points(lat, lon, ox, oy, start, rx, ry, segments))
    return points


def _encode_layer(style: str, ring: list[Point]) -> str:
    """Encode one closed ring as 'S <STYLE> M<lat>,<lon> L<dlat>,<dlon> ... Z'.

    The first vertex is absolute; every following vertex is a delta from the
    previous one (SVG relative-lineto convention) — compact, and the client
    parses it by walking the string once. Longitude deltas go through
    _delta_lon so a ring that legitimately crosses the +-180 meridian (real
    LROC outlines can) doesn't produce a huge wraparound jump.
    """
    parts = [f"S {style}"]
    prev_lat: float | None = None
    prev_lon = 0.0
    for lon, lat in ring:
        lat_r = round(lat, 4)
        if prev_lat is None:
            lon_r = round(_normalize_lon(lon), 4)
            parts.append(f"M{lat_r},{lon_r}")
        else:
            dlat = round(lat_r - prev_lat, 4)
            dlon = round(_delta_lon(lon, prev_lon), 4)
            parts.append(f"L{dlat},{dlon}")
            lon_r = round(prev_lon + dlon, 4)
        prev_lat, prev_lon = lat_r, lon_r
    parts.append("Z")
    return " ".join(parts)


def _valid_polygons(rings: list[list[Point]]) -> list[Polygon]:
    """Build shapely Polygons from rings, dropping degenerate ones and
    fixing minor self-intersections (buffer(0)) rather than raising —
    real digitized outlines occasionally have these after simplification."""
    polys: list[Polygon] = []
    for ring in rings:
        if len(ring) < 3:
            continue
        poly = Polygon(ring)
        if not poly.is_valid:
            poly = poly.buffer(0)
        if not poly.is_empty:
            polys.append(poly)
    return polys


def _subtract_obstacles(ring: list[Point], obstacle_polys: list[Polygon]) -> list[list[Point]]:
    """Subtract overlapping sea/crater polygons from a mons ridge ring.

    The Gazetteer only gives mons/montes a bounding box (see
    _ridge_outline) — real ridges don't actually run through the middle of
    a sea or over a named crater, so this trims that synthetic box against
    real geometry the pipeline already computed for those types. A cut that
    fully bisects the ridge yields more than one returned ring (encoded as
    separate `geom` layers — see moon_pipeline.md). Holes (an obstacle
    entirely enclosed by the ridge, touching no edge) are dropped rather
    than represented — the `geom` format has no hole support, and this is
    rare enough for an already-approximate bounding-box shape not to be
    worth adding it for.
    """
    poly = Polygon(ring)
    if not poly.is_valid:
        poly = poly.buffer(0)
    if poly.is_empty:
        return [ring]
    overlapping = [o for o in obstacle_polys if o.intersects(poly)]
    if not overlapping:
        return [ring]
    remainder = poly.difference(unary_union(overlapping))
    if remainder.is_empty:
        return [ring]
    if isinstance(remainder, MultiPolygon):
        pieces: list[Polygon] = list(remainder.geoms)
    else:
        pieces = [remainder]  # type: ignore[list-item]
    rings: list[list[Point]] = []
    for piece in pieces:
        if not isinstance(piece, Polygon) or piece.is_empty or piece.area < 1e-9:
            continue
        # Drop the closing duplicate vertex.
        coords: list[Point] = list(piece.exterior.coords)[:-1]  # type: ignore[assignment]
        simplified = _simplify_to_max_points(coords, MOON_OUTLINE_MAX_POINTS)
        if len(simplified) >= 3:
            rings.append(simplified)
    return rings or [ring]


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
    def _selenographic_size_deg(diam_km: float) -> float:
        """Return angular diameter in degrees as seen from the Moon's own
        centre (i.e. the feature's real angular extent on the lunar surface,
        not its apparent size as seen from Earth)."""
        return math.degrees(diam_km / MOON_RADIUS_KM)

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
    def _compute_size_axes(row: dict[str, str], diam_deg: float, lat: float) -> tuple[float, float]:
        min_lat = _float_or_none(row.get("min_lat", ""))
        max_lat = _float_or_none(row.get("max_lat", ""))
        min_lon = _float_or_none(row.get("min_lon", ""))
        max_lon = _float_or_none(row.get("max_lon", ""))
        # Near a pole, a physically small feature's min/max longitude can
        # legitimately span most or all of 0-360 deg (every meridian passes
        # through the pole) — e.g. Peary at lat 88.6 deg records a 141 deg
        # "width" for an ~75 km crater. That's not a real elongated shape,
        # just a degenerate bounding box; a bogus width that large feeds the
        # ratio check below into treating it as a huge ellipse. Fall back to
        # the diam-based circular estimate the same way "no bounds at all"
        # already does, rather than trusting longitude at all this close to
        # the pole (cos(lat) below is too small/noise-sensitive there to
        # correct reliably).
        near_pole = (max_lat is not None and abs(max_lat) >= MOON_POLAR_LAT_GUARD_DEG) or (
            min_lat is not None and abs(min_lat) >= MOON_POLAR_LAT_GUARD_DEG
        )
        if not near_pole and None not in (min_lat, max_lat, min_lon, max_lon):
            # A degree of longitude is only as physically wide as a degree of
            # latitude at the equator — at latitude phi it's cos(phi) times
            # narrower (meridians converge toward the poles), so the raw
            # longitude span isn't directly comparable to the latitude span
            # without this correction. Skipping it inflates any feature's
            # reported width by 1/cos(lat), which — since a genuinely
            # circular crater's inflated "width" then exceeds its true
            # height — gets it wrongly classified as elongated and rendered
            # from the inflated width instead of its real diameter (e.g.
            # Schrodinger at lat -74.7 recorded a raw 41 deg "width" for a
            # crater whose real angular size, matching its height, is ~10
            # deg — a >4x size inflation before this fix).
            lon_span = _lon_span_deg(float(min_lon), float(max_lon))  # type: ignore[arg-type]
            width = lon_span * math.cos(math.radians(lat))
            height = abs(float(max_lat) - float(min_lat))  # type: ignore[arg-type]
            return width, height
        return diam_deg, diam_deg

    @staticmethod
    def _parse_placemark(
        placemark: Any,
        ns: dict[str, str],
        allowed: set[str],
        min_size_km: float,
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
        diam_deg = MoonFeaturePipeline._selenographic_size_deg(diam_km)
        width, height = MoonFeaturePipeline._compute_size_axes(row, diam_deg, lat)
        km_per_deg = MOON_RADIUS_KM * math.pi / 180.0
        if max(width, height) * km_per_deg < min_size_km:
            return None
        return {
            "name": name,
            "type": MOON_TYPE_ALIASES.get(feature_type, feature_type),
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
        min_size_km = MOON_MIN_ITEM_SIZE_KM if min_item_size is None else min_item_size
        with zipfile.ZipFile(source) as zf:
            kml_name = next(name for name in zf.namelist() if name.endswith(".kml"))
            # Source is a fixed USGS/IAU Gazetteer KMZ over HTTPS.
            root = ET.fromstring(zf.read(kml_name))  # noqa: S314
        ns = {"kml": "http://www.opengis.net/kml/2.2"}
        for placemark in root.findall(".//kml:Placemark", ns):
            feature = self._parse_placemark(placemark, ns, allowed, min_size_km)
            if feature is not None:
                out.append(feature)
        out.sort(key=lambda f: (f["type"], f["name"]))
        return out

    @staticmethod
    def _synthesize_ring(
        feature: dict[str, Any], lat: float, lon: float, type_key: str, style: str
    ) -> tuple[list[Point], str]:
        """Build a ring for a feature with no digitized outline: a circle,
        a ridge outline, a filled rectangle, or a raised circle, depending
        on its aspect ratio and type."""
        width = float(feature["size_axes"][0])
        height = float(feature["size_axes"][1])
        max_axis = max(width, height)
        min_axis = min(width, height)
        ratio = (max_axis / min_axis) if min_axis > 0 else float("inf")

        if ratio <= MOON_CIRCULAR_TOLERANCE:
            radius = (width + height) / 4.0
            return _circle_ring(lat, lon, radius, MOON_CIRCLE_VERTEX_COUNT), style

        if type_key in MOON_RIDGE_LIKE_TYPES:
            ring = _ridge_outline(
                lat, lon, width, height, MOON_RIDGE_CORNER_RADIUS_RATIO, MOON_RIDGE_CORNER_SEGMENTS
            )
            return ring, STYLE_FILLED

        if style == STYLE_FILLED:
            half_w = width / 2.0
            half_h = height / 2.0
            ring = [
                (lon - half_w, lat - half_h),
                (lon + half_w, lat - half_h),
                (lon + half_w, lat + half_h),
                (lon - half_w, lat + half_h),
            ]
            return ring, STYLE_FILLED

        radius = max_axis / 2.0
        return _circle_ring(lat, lon, radius, MOON_CIRCLE_VERTEX_COUNT), STYLE_RAISED

    @staticmethod
    def _feature_ring(
        feature: dict[str, Any], outline: list[Point] | None, type_key: str
    ) -> tuple[list[Point], str]:
        """Return a feature's base (ring, style) — before any mons-specific
        obstacle subtraction, which _group_features applies afterward once
        every other type's ring is known (see _subtract_obstacles)."""
        lat = float(feature["lat"])
        lon = float(feature["lon"])
        is_filled = type_key in MOON_AREA_TYPES or type_key in MOON_RIDGE_LIKE_TYPES
        style = STYLE_FILLED if is_filled else STYLE_RAISED

        if outline:
            return outline, style

        return MoonFeaturePipeline._synthesize_ring(feature, lat, lon, type_key, style)

    @staticmethod
    def _round_feature(
        feature: dict[str, Any], rings: list[list[Point]], style: str
    ) -> dict[str, Any]:
        """Round a Moon feature into its final compact record: lat/lon plus
        `geom`, one styled `S <STYLE> M/L/Z` path string per ring (see
        moon_pipeline.md). Every feature has exactly one ring except
        mons/montes after obstacle subtraction, which can split a ridge
        into several disconnected pieces.
        """
        width_deg, height_deg = feature["size_axes"]
        km_per_deg = MOON_RADIUS_KM * math.pi / 180.0
        width_km = float(width_deg) * km_per_deg
        height_km = float(height_deg) * km_per_deg
        max_axis = max(width_km, height_km)
        min_axis = min(width_km, height_km)
        ratio = (max_axis / min_axis) if min_axis > 0 else float("inf")

        out: dict[str, Any] = {
            "lat": round(float(feature["lat"]), 4),
            "lon": round(float(feature["lon"]), 4),
            # Physical size in km, for display (README/moon_map.md) — derived
            # from the same width/height _feature_ring uses for its own
            # circular/elongated rendering choice, so the two never disagree.
            "size_km": [round(width_km, 2), round(height_km, 2)],
            "circular": ratio <= MOON_CIRCULAR_TOLERANCE,
        }
        out["geom"] = [_encode_layer(style, ring) for ring in rings if len(ring) >= 3]
        return out

    @staticmethod
    def _group_features(
        features: list[dict[str, Any]], outlines: dict[str, list[Point]]
    ) -> dict[str, dict[str, Any]]:
        """Group features by lowercase type and then by feature name.

        Two passes: every non-ridge-like feature is rounded first (unchanged
        geometry rules), collecting sea (MOON_AREA_TYPES) and crater rings
        along the way; ridge-like features (mons/montes, catena, vallis —
        see MOON_RIDGE_LIKE_TYPES) are rounded last, with those rings
        subtracted from each one's own ridge outline (see
        _subtract_obstacles) so a mountain range, crater chain, or valley —
        whose only source data is an imprecise bounding box — never
        visually overlaps a real sea or crater boundary. Ridge-like features
        are never obstacles to each other (e.g. Vallis Alpes genuinely runs
        through Montes Alpes on the real Moon — that intersection is
        correct, not a rendering bug to subtract away).
        """
        grouped: dict[str, dict[str, Any]] = {}
        ridge_features: list[tuple[dict[str, Any], str]] = []
        obstacle_rings: list[list[Point]] = []

        for feature in features:
            type_key = feature["type"].lower()
            if type_key in MOON_RIDGE_LIKE_TYPES:
                ridge_features.append((feature, type_key))
                continue
            outline = outlines.get(feature["name"]) if type_key in MOON_AREA_TYPES else None
            ring, style = MoonFeaturePipeline._feature_ring(feature, outline, type_key)
            grouped.setdefault(type_key, {})[feature["name"]] = MoonFeaturePipeline._round_feature(
                feature, [ring], style
            )
            if type_key in MOON_AREA_TYPES or type_key == "crater":
                obstacle_rings.append(ring)

        obstacle_polys = _valid_polygons(obstacle_rings)
        for feature, type_key in ridge_features:
            ring, style = MoonFeaturePipeline._feature_ring(feature, None, type_key)
            rings = _subtract_obstacles(ring, obstacle_polys)
            grouped.setdefault(type_key, {})[feature["name"]] = MoonFeaturePipeline._round_feature(
                feature, rings, style
            )

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
