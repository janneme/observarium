#!/usr/bin/env python3
"""Diagnostic tool for the Visual Range feature's guide-path algorithm.

Answers one question: for a given telescope/eyepiece and a given start star,
is there actually enough usable star field around it to build a measuring
plan (client/src/lib/visualRangePlan.js), or does the app's guide-path BFS
fail even though the raw star field would support it?

For each half-magnitude step from --start-mag to --end-mag, prints how many
candidate stars survive three progressively stricter filters, all mirroring
the real algorithm's own rules as closely as a static, single-position
analysis can:

  1. Total       - stars within --fov-neighbourhood FOV-radii of --star,
                   magnitude within +/- --mag-tollerance of the row, and
                   passing the same per-star eligibility rules
                   generatePlan()'s getCandidates() applies: isolated from
                   any brighter star nearby, not overlapping a large
                   low-surface-brightness DSO, not a known variable star,
                   not one of the two most extreme blue/red colour bins.
  2. In pair      - of those, stars that have another Total-category star
                   within one real telescope FOV radius of themselves (i.e.
                   both would be visible together if this star were centred
                   in the eyepiece) - the guide-path algorithm always moves
                   between *pairs* of mutually-visible guide stars, never a
                   single one.
  3. In pair,     - of those, stars where no star of any magnitude within
     no bright      one FOV radius is brighter than this star by more than
                   --disabling-mag-diff - mirrors checkMaxMagDiff(), which
                   the real algorithm uses to reject a position where a much
                   brighter star would dominate/wash out the view.

If "In pair, no bright" stays healthy across the whole magnitude range but
Observarium still reports "no guide path found", the bottleneck is in the
BFS/step-chaining logic itself (findGuidePath, the phase-2 step chain, the
lastHopClear/endpoint checks, etc.), not a genuine lack of usable stars.

Data source: data_prep/output/stars_t1.mNN.csv, stars_t2.mNN.csv and
dso.json (the smallest NN tier that covers --end-mag is picked
automatically). Run with the server project's venv, e.g.:

    server/.venv/bin/python3 scripts/visual_range_analysis.py \\
        --telescope 150/750 --eyepiece 25/50 --star Mizar

No third-party dependencies are required (stdlib only), so any Python
3.12+ interpreter works - "server .venv" is just a convenient one already
present in the repo.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR_DEFAULT = REPO_ROOT / "data_prep" / "output"

MAG_STEP = 0.5

# Mirrors visualRangePlan.js's constants exactly, so "candidate eligibility"
# here means the same thing it means to the real algorithm.
CLOSE_NEIGHBOURHOOD_REL_RADIUS = 0.02  # isolation / DSO-margin radius = this * fovDeg
DSO_MAX_SB = 24.0
# COLOR_PALETTE indices 0 and 6 (client/src/lib/db.js) - the bluest and reddest bins.
CLR_BLUEST_IDX = 0
CLR_REDDEST_IDX = 6
DSO_EXCLUDED_TYPES = {
    "galaxy",
    "spiral galaxy",
    "elliptical galaxy",
    "lenticular galaxy",
    "irregular galaxy",
    "emission nebula",
    "reflection nebula",
    "bright nebula",
    "planetary nebula",
    "supernova remnant",
    "globular cluster",
}

AVAILABLE_TIERS = (9, 12, 14)


@dataclass
class Star:
    id: str
    ra: float
    dec: float
    mag: float
    clr: int | None
    name: str | None = None
    var_type: str | None = None


@dataclass
class SignificantDso:
    ra: float
    dec: float
    radius_deg: float


@dataclass
class Args:
    telescope_diameter_mm: float
    telescope_focal_mm: float
    eyepiece_focal_mm: float
    eyepiece_afov_deg: float
    star_name: str
    mag_tollerance: float
    start_mag: float
    end_mag: float
    fov_neighbourhood: float
    disabling_mag_diff: float
    data_dir: Path


def ang_sep_deg(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    """Great-circle separation in degrees (same haversine form as angSepDeg in
    visualRangePlan.js)."""
    phi1 = math.radians(dec1)
    phi2 = math.radians(dec2)
    d_phi = math.radians(dec2 - dec1)
    d_lam = math.radians(ra2 - ra1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    return 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)) * 180 / math.pi


def parse_ratio(raw: str, flag: str) -> tuple[float, float]:
    parts = raw.split("/")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"{flag} must be in the form A/B, got {raw!r}")
    try:
        return float(parts[0]), float(parts[1])
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"{flag} must be numeric A/B, got {raw!r}") from e


def pick_tier(end_mag: float) -> int:
    needed = math.ceil(end_mag)
    for tier in AVAILABLE_TIERS:
        if tier >= needed:
            return tier
    return AVAILABLE_TIERS[-1]


def load_t1(path: Path) -> list[Star]:
    stars: list[Star] = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)  # header: ra,de,mg,cl,hp,hd,sp,ds,pr,pd,fl,by,db,nm,nt,sm,cn,vt,vp
        for i, row in enumerate(reader):
            # Trailing empty columns (nt/sm/cn/vt/vp) are dropped entirely by
            # the CSV writer rather than kept as empty fields, so row length
            # varies - pad rather than skip, or most rows with no notes/vartype
            # (i.e. most rows) would be silently dropped.
            if len(row) < 19:
                row = row + [""] * (19 - len(row))
            try:
                ra = float(row[0])
                dec = float(row[1])
                mag = float(row[2])
            except ValueError:
                continue
            clr = int(row[3]) if row[3] else None
            name = row[13].strip() or None
            var_type = row[17].strip() or None
            stars.append(
                Star(id=f"t1_{i}", ra=ra, dec=dec, mag=mag, clr=clr, name=name, var_type=var_type)
            )
    return stars


def load_t2_filtered(
    path: Path, ra_center: float, dec_center: float, box_radius_deg: float
) -> list[Star]:
    """Streams the (large) T2 CSV, keeping only rows within a generous flat
    RA/Dec box around the target - a coarse, non-cos(dec)-corrected filter
    (same simplification the client test harness uses), safe here because
    the real angular-separation check happens later wherever it matters."""
    stars: list[Star] = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)  # header: z,ra,de,mg,cl,hp,hd,sp,ds,pr,pd
        for i, row in enumerate(reader):
            if len(row) < 5:
                continue
            try:
                ra = float(row[1])
                dec = float(row[2])
            except ValueError:
                continue
            if abs(dec - dec_center) > box_radius_deg:
                continue
            d_ra = abs(ra - ra_center)
            if min(d_ra, 360 - d_ra) > box_radius_deg:
                continue
            try:
                mag = float(row[3])
            except ValueError:
                continue
            clr = int(row[4]) if row[4] else None
            stars.append(Star(id=f"t2_{i}", ra=ra, dec=dec, mag=mag, clr=clr))
    return stars


def load_significant_dsos(path: Path) -> list[SignificantDso]:
    """Mirrors visualRangePlan.js's computeSignificantDsos() exactly."""
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    result: list[SignificantDso] = []
    for dsos in raw.values():
        for dso in dsos:
            dso_type = dso.get("type")
            if dso_type not in DSO_EXCLUDED_TYPES:
                continue
            mag = dso.get("mag")
            if isinstance(mag, list):
                mag = mag[0] if mag else None
            if mag is None:
                continue
            size = dso.get("size")
            if size is None:
                continue
            if isinstance(size, list):
                a, b = size[0] / 2, size[1] / 2
            else:
                a = b = size / 2
            if a <= 0 or b <= 0:
                continue
            sb = mag + 2.5 * math.log10(math.pi * (a * 30) * (b * 30))
            if sb < DSO_MAX_SB:
                ra_deg = dso["pos"][0] * 15  # dso.json stores RA in hours
                dec_deg = dso["pos"][1]
                result.append(SignificantDso(ra=ra_deg, dec=dec_deg, radius_deg=a / 60))
    return result


def find_star_by_name(t1_stars: list[Star], name: str) -> Star | None:
    target = name.strip().lower()
    for s in t1_stars:
        if s.name and s.name.strip().lower() == target:
            return s
    return None


class SpatialGrid:
    """Flat RA/Dec grid index (mirrors visualRangePlan.js's coarse/fine bucket
    indexes) so radius queries don't have to scan every loaded star - without
    it, is_isolated()/the "no bright" check turn into an O(candidates *
    all_stars) scan that's fine for a sparse field near the pole but can take
    minutes in a rich Milky Way field.

    RA cells wrap around at 360 deg, and the RA search span is widened by
    1/cos(dec) (using the search disc's pole-ward edge, so it's a safe
    over-estimate): near the equator 1 deg of RA is ~1 deg of sky, but near
    the pole it's much less, so a search that only widened by a flat
    +/-radius_deg in RA would silently miss real neighbours at high
    declination - which is exactly the kind of star this tool is meant to
    analyze (Mizar is at dec +55, for one)."""

    def __init__(self, stars: list[Star], cell_deg: float):
        self.cell_deg = max(cell_deg, 1e-6)
        self.ra_cells = max(1, math.ceil(360.0 / self.cell_deg))
        self.buckets: dict[tuple[int, int], list[Star]] = {}
        for s in stars:
            self.buckets.setdefault(self._key(s.ra, s.dec), []).append(s)

    def _key(self, ra: float, dec: float) -> tuple[int, int]:
        c_ra = int((ra % 360.0) / self.cell_deg) % self.ra_cells
        c_dec = int(math.floor(dec / self.cell_deg))
        return (c_ra, c_dec)

    def query(self, ra: float, dec: float, radius_deg: float) -> list[Star]:
        dec_span = max(1, int(math.ceil(radius_deg / self.cell_deg)))
        edge_dec = min(abs(dec) + radius_deg, 89.9)
        cos_dec = max(math.cos(math.radians(edge_dec)), 0.01)
        ra_span = min(
            max(1, int(math.ceil(radius_deg / (self.cell_deg * cos_dec)))),
            self.ra_cells // 2,
        )

        c_ra, c_dec = self._key(ra, dec)
        seen_ids: set[str] = set()
        results: list[Star] = []
        for d_dec in range(-dec_span, dec_span + 1):
            for d_ra in range(-ra_span, ra_span + 1):
                bucket = self.buckets.get(((c_ra + d_ra) % self.ra_cells, c_dec + d_dec))
                if not bucket:
                    continue
                for s in bucket:
                    if s.id in seen_ids:
                        continue
                    if ang_sep_deg(ra, dec, s.ra, s.dec) <= radius_deg:
                        seen_ids.add(s.id)
                        results.append(s)
        return results


def is_isolated(star: Star, fine_grid: SpatialGrid, isol_radius_deg: float) -> bool:
    for other in fine_grid.query(star.ra, star.dec, isol_radius_deg):
        if other.id == star.id:
            continue
        if other.mag < star.mag:
            return False
    return True


def not_in_dso(star: Star, dsos: list[SignificantDso], margin_deg: float) -> bool:
    for dso in dsos:
        if ang_sep_deg(star.ra, star.dec, dso.ra, dso.dec) < dso.radius_deg + margin_deg:
            return False
    return True


def build_pools(
    all_stars: list[Star],
    fine_grid: SpatialGrid,
    coarse_grid: SpatialGrid,
    target: Star,
    neighbourhood_radius_deg: float,
    isol_radius_deg: float,
    dso_margin_deg: float,
    dsos: list[SignificantDso],
    fov_radius_deg: float,
    mag_row: float,
    mag_tollerance: float,
    disabling_mag_diff: float,
) -> tuple[int, int, int]:
    mag_lo = mag_row - mag_tollerance
    mag_hi = mag_row + mag_tollerance

    in_neighbourhood = [
        s
        for s in all_stars
        if s.id != target.id
        and ang_sep_deg(target.ra, target.dec, s.ra, s.dec) <= neighbourhood_radius_deg
    ]

    total_pool: list[Star] = []
    for s in in_neighbourhood:
        if not (mag_lo <= s.mag <= mag_hi):
            continue
        if s.var_type:
            continue
        if s.clr in (CLR_BLUEST_IDX, CLR_REDDEST_IDX):
            continue
        if not is_isolated(s, fine_grid, isol_radius_deg):
            continue
        if not not_in_dso(s, dsos, dso_margin_deg):
            continue
        total_pool.append(s)

    in_pair: list[Star] = []
    for s in total_pool:
        has_partner = any(
            other.id != s.id and ang_sep_deg(s.ra, s.dec, other.ra, other.dec) <= fov_radius_deg
            for other in total_pool
        )
        if has_partner:
            in_pair.append(s)

    no_bright: list[Star] = []
    for s in in_pair:
        nearby = coarse_grid.query(s.ra, s.dec, fov_radius_deg)
        brightest = min((o.mag for o in nearby if o.id != s.id), default=math.inf)
        if s.mag - brightest <= disabling_mag_diff:
            no_bright.append(s)

    return len(total_pool), len(in_pair), len(no_bright)


def parse_args(argv: list[str]) -> Args:
    parser = argparse.ArgumentParser(
        prog="visual_range_analysis.py",
        description=(
            "Diagnoses whether the Visual Range guide-path algorithm's failure to find a "
            "measuring plan for a given star is due to a sparse star field or a bug in the "
            "algorithm itself. Prints a table of candidate-star counts per magnitude step, "
            "under three progressively stricter filters matching visualRangePlan.js."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--telescope",
        required=True,
        type=lambda s: parse_ratio(s, "--telescope"),
        metavar="DIAMETER_MM/FOCAL_MM",
        help="Telescope aperture diameter and focal length in millimetres, e.g. 150/750.",
    )
    parser.add_argument(
        "--eyepiece",
        required=True,
        type=lambda s: parse_ratio(s, "--eyepiece"),
        metavar="FOCAL_MM/AFOV_DEG",
        help="Eyepiece focal length in millimetres and apparent field of view in degrees, "
        "e.g. 25/50.",
    )
    parser.add_argument(
        "--star",
        required=True,
        metavar="NAME",
        help="Name of the star whose neighbourhood is analyzed (matched against the T1 "
        "catalogue's proper-name column), e.g. Mizar.",
    )
    parser.add_argument(
        "--mag-tollerance",
        type=float,
        default=0.15,
        metavar="MAG",
        help="Half-width of the magnitude window around each table row: a row for magnitude "
        "M counts stars with mag in [M-MAG, M+MAG].",
    )
    parser.add_argument(
        "--start-mag",
        type=float,
        default=9.0,
        metavar="MAG",
        help="First (brightest) magnitude row in the table.",
    )
    parser.add_argument(
        "--end-mag",
        type=float,
        default=14.0,
        metavar="MAG",
        help="Last (faintest) magnitude row in the table. Rows step by 0.5 from --start-mag "
        "to --end-mag.",
    )
    parser.add_argument(
        "--fov-neighbourhood",
        type=float,
        default=5.0,
        metavar="FACTOR",
        help="How far around --star to search for candidate stars, as a multiple of the "
        "telescope+eyepiece's FOV radius.",
    )
    parser.add_argument(
        "--disabling-mag-diff",
        type=float,
        default=5.0,
        metavar="MAG",
        help="A candidate star is disqualified from the 'In pair, no bright' column if some "
        "star within one FOV radius is brighter than it by more than this many magnitudes.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DATA_DIR_DEFAULT,
        metavar="DIR",
        help="Directory containing stars_t1.mNN.csv / stars_t2.mNN.csv / dso.json.",
    )

    ns = parser.parse_args(argv)

    diameter_mm, focal_mm = ns.telescope
    eyepiece_focal_mm, afov_deg = ns.eyepiece

    return Args(
        telescope_diameter_mm=diameter_mm,
        telescope_focal_mm=focal_mm,
        eyepiece_focal_mm=eyepiece_focal_mm,
        eyepiece_afov_deg=afov_deg,
        star_name=ns.star,
        mag_tollerance=ns.mag_tollerance,
        start_mag=ns.start_mag,
        end_mag=ns.end_mag,
        fov_neighbourhood=ns.fov_neighbourhood,
        disabling_mag_diff=ns.disabling_mag_diff,
        data_dir=ns.data_dir,
    )


def mag_rows(start_mag: float, end_mag: float) -> list[float]:
    n_steps = round((end_mag - start_mag) / MAG_STEP)
    return [round(start_mag + i * MAG_STEP, 2) for i in range(n_steps + 1)]


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    magnification = args.telescope_focal_mm / args.eyepiece_focal_mm
    fov_deg = args.eyepiece_afov_deg / magnification
    fov_radius_deg = fov_deg / 2
    neighbourhood_radius_deg = args.fov_neighbourhood * fov_radius_deg
    isol_radius_deg = CLOSE_NEIGHBOURHOOD_REL_RADIUS * fov_deg
    theoretical_max_mag = 2.1 + 5 * math.log10(
        args.telescope_diameter_mm
    )  # diameter in mm, same formula as the app

    tier = pick_tier(args.end_mag)
    t1_path = args.data_dir / f"stars_t1.m{tier}.csv"
    t2_path = args.data_dir / f"stars_t2.m{tier}.csv"
    dso_path = args.data_dir / "dso.json"
    for p in (t1_path, t2_path):
        if not p.exists():
            print(f"error: catalogue file not found: {p}", file=sys.stderr)
            return 1

    t1_stars = load_t1(t1_path)
    target = find_star_by_name(t1_stars, args.star_name)
    if target is None:
        print(
            f"error: star {args.star_name!r} not found by name in {t1_path.name}", file=sys.stderr
        )
        return 1

    box_margin_deg = neighbourhood_radius_deg + fov_deg
    t2_stars = load_t2_filtered(t2_path, target.ra, target.dec, box_margin_deg)
    t1_in_box = [s for s in t1_stars if abs(s.dec - target.dec) <= box_margin_deg]
    all_stars = t1_in_box + t2_stars

    dsos = load_significant_dsos(dso_path)
    dso_margin_deg = isol_radius_deg

    fine_grid = SpatialGrid(all_stars, cell_deg=isol_radius_deg)
    coarse_grid = SpatialGrid(all_stars, cell_deg=fov_radius_deg)

    print(
        f"Star:              {args.star_name} "
        f"(RA {target.ra:.4f}, Dec {target.dec:+.4f}, mag {target.mag:.2f})"
    )
    print(
        f"Telescope:         {args.telescope_diameter_mm:.0f}mm / {args.telescope_focal_mm:.0f}mm "
        f"(f/{args.telescope_focal_mm / args.telescope_diameter_mm:.1f}), "
        f"theoretical limit mag {theoretical_max_mag:.1f}"
    )
    print(
        f"Eyepiece:          {args.eyepiece_focal_mm:.0f}mm, AFOV {args.eyepiece_afov_deg:.0f} deg"
    )
    print(f"Magnification:     {magnification:.0f}x")
    print(f"True FOV:          {fov_deg:.3f} deg (radius {fov_radius_deg:.3f} deg)")
    print(
        f"Neighbourhood:     {args.fov_neighbourhood:.1f}x FOV radius = "
        f"{neighbourhood_radius_deg:.3f} deg"
    )
    print(f"Isolation radius:  {isol_radius_deg:.4f} deg (2% of FOV, same as the app)")
    print(f"Mag tollerance:    +/- {args.mag_tollerance}")
    print(f"Disabling mag diff: {args.disabling_mag_diff}")
    print(
        f"Catalogue tier:    m{tier}  "
        f"({len(t1_stars)} T1 stars, {len(t2_stars)} T2 stars in search box)"
    )
    print(f"Significant DSOs:  {len(dsos)}")
    print()

    header = f"{'Mag':>6} | {'Total':>7} | {'In pair':>7} | {'In pair, no bright':>19}"
    print(header)
    print("-" * len(header))
    for m in mag_rows(args.start_mag, args.end_mag):
        total, in_pair, no_bright = build_pools(
            all_stars,
            fine_grid,
            coarse_grid,
            target,
            neighbourhood_radius_deg,
            isol_radius_deg,
            dso_margin_deg,
            dsos,
            fov_radius_deg,
            m,
            args.mag_tollerance,
            args.disabling_mag_diff,
        )
        print(f"{m:>6.1f} | {total:>7} | {in_pair:>7} | {no_bright:>19}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
