"""Constellation pipeline: Stellarium modern_iau index -> constellations.json."""

import json
from pathlib import Path
from typing import Any

from config import CONSTELLATIONS_IAU_FILENAME, CONSTELLATIONS_IAU_URL
from downloader import Downloader


def _line_pairs(vertices: list[int]) -> list[list[int]]:
    """Convert a polyline vertex list to edge pairs of HIP identifiers."""
    if len(vertices) < 2:
        return []
    return [[vertices[idx], vertices[idx + 1]] for idx in range(len(vertices) - 1)]


def _parse_edge_record(record: str) -> tuple[str, str, str, str, str, str]:
    """Parse one Stellarium edge record.

    Example::
        001:002 M+ 22:52:00 +34:30:00 22:52:00 +52:30:00 AND LAC
    """
    parts = record.split()
    if len(parts) < 8:
        raise ValueError(f"Invalid boundary edge record: {record!r}")
    return parts[2], parts[3], parts[4], parts[5], parts[6], parts[7]


def _precess_b1875_to_j2000(ra_hms: str, dec_dms: str) -> tuple[float, float]:
    """Precess one B1875 coordinate pair to J2000/ICRS."""
    try:
        # pylint: disable=import-outside-toplevel
        from astropy.coordinates import FK5, SkyCoord
    except ImportError as exc:  # pragma: no cover - exercised in integration runs
        raise RuntimeError(
            "astropy is required for B1875->J2000 constellation boundary precession"
        ) from exc

    coord = SkyCoord(
        ra=ra_hms,
        dec=dec_dms,
        unit=("hourangle", "deg"),
        frame=FK5(equinox="B1875"),
    )
    icrs = coord.icrs
    return icrs.ra.hour, icrs.dec.deg


class ConstellationPipeline:
    """Build constellation lines, boundaries and names from Stellarium data."""

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

    def run(self) -> Path:
        """Execute full pipeline and return output file path."""
        index_path = self._downloader.fetch(CONSTELLATIONS_IAU_URL, CONSTELLATIONS_IAU_FILENAME)
        with index_path.open(encoding="utf-8") as fh:
            index = json.load(fh)
        constellations = self._build(index)
        return self._write(constellations)

    def _build(self, index: dict[str, Any]) -> dict[str, dict[str, Any]]:
        constellations, code_map = self._build_constellation_base(index)
        self._append_boundary_edges(index, constellations, code_map)
        return dict(sorted(constellations.items()))

    def _build_constellation_base(
        self,
        index: dict[str, Any],
    ) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
        constellations: dict[str, dict[str, Any]] = {}
        code_map: dict[str, str] = {}
        for item in index.get("constellations", []):
            code, data = self._constellation_from_item(item)
            code_map[code.upper()] = code
            constellations[code] = data
        return constellations, code_map

    @staticmethod
    def _constellation_from_item(item: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        """Build one constellation object from one Stellarium constellation entry."""
        code = item["id"].split()[-1]
        common_name = item.get("common_name", {})
        name = common_name.get("native") or common_name.get("english") or code
        lines: list[list[int]] = []
        for polyline in item.get("lines", []):
            lines.extend(_line_pairs(polyline))
        data: dict[str, Any] = {
            "name": name,
            "lines": lines,
            "bounds": [],
        }
        byname = common_name.get("byname")
        if byname:
            data["common"] = byname
        return code, data

    def _append_boundary_edges(
        self,
        index: dict[str, Any],
        constellations: dict[str, dict[str, Any]],
        code_map: dict[str, str],
    ) -> None:
        coord_cache: dict[tuple[str, str], tuple[float, float]] = {}
        for edge in index.get("edges", []):
            segment, raw_codes = self._edge_segment(edge, coord_cache)
            for raw_code in raw_codes:
                code = code_map.get(raw_code.upper())
                if code is not None:
                    constellations[code]["bounds"].append(segment)

    def _edge_segment(
        self,
        edge: str,
        coord_cache: dict[tuple[str, str], tuple[float, float]],
    ) -> tuple[list[list[float]], tuple[str, str]]:
        ra1, dec1, ra2, dec2, left, right = _parse_edge_record(edge)
        p1 = self._precess_cached(ra1, dec1, coord_cache)
        p2 = self._precess_cached(ra2, dec2, coord_cache)
        return [[p1[0], p1[1]], [p2[0], p2[1]]], (left, right)

    @staticmethod
    def _precess_cached(
        ra_hms: str,
        dec_dms: str,
        cache: dict[tuple[str, str], tuple[float, float]],
    ) -> tuple[float, float]:
        key = (ra_hms, dec_dms)
        point = cache.get(key)
        if point is None:
            point = _precess_b1875_to_j2000(ra_hms, dec_dms)
            cache[key] = point
        return point

    def _write(self, constellations: dict[str, dict[str, Any]]) -> Path:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        out = self._output_dir / "constellations.json"
        with out.open("w", encoding="utf-8") as fh:
            json.dump(constellations, fh, ensure_ascii=False)
        n_lines = sum(len(obj["lines"]) for obj in constellations.values())
        n_bounds = sum(len(obj["bounds"]) for obj in constellations.values())
        print(f"Constellations : {len(constellations):,}")
        print(f"Line segments  : {n_lines:,}")
        print(f"Boundary edges : {n_bounds:,}")
        print(f"Output         : {out} ({out.stat().st_size / 1_048_576:.2f} MB)")
        return out
