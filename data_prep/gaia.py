"""Gaia DR3 async TAP downloader for the star catalogue supplement.

Downloads stars from Gaia DR3 that are absent from AT-HYG, filling the
magnitude gap between the AT-HYG / Tycho-2 ceiling (~V 11.5) and the
requested max magnitude (up to ~14 for telescope simulation).

Deduplication strategy: AT-HYG is built from Tycho-2 and is complete to
V ≈ 11.5.  We query Gaia with phot_g_mean_mag > min_mag (default 11.5) so
the downloaded stars are overwhelmingly absent from AT-HYG.  A JOIN against
gaiadr3.tycho2tdsc_merge would be more precise but is extremely slow for
millions of rows and unnecessary given the ≈0.5-mag G−V spread.

Workflow (IVOA TAP async):
    1. POST query to TAP async endpoint → 303 redirect to job URL
    2. urllib follows redirect; resp.geturl() captures the job URL
    3. Poll {job_url}/phase until COMPLETED / ERROR / ABORTED
    4. On ERROR fetch {job_url}/error for diagnostics, then raise
    5. Download {job_url}/results/result (CSV) and cache as gzip
"""

import csv
import gzip
import math
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

_GAIA_TAP_ASYNC = "https://gea.esac.esa.int/tap-server/tap/async"
_POLL_INTERVAL_S = 15   # seconds between phase-checks
_POLL_TIMEOUT_S = 7200  # 2-hour hard limit

# Gaia Bp-Rp → COLOR_PALETTE index thresholds (approximate MK spectral class).
# Must mirror the COLOR_PALETTE ordering in stars.py.
_BP_RP_THRESHOLDS: list[tuple[float, int]] = [
    (-0.10, 0),   # O: deep blue
    ( 0.15, 1),   # B: blue-white
    ( 0.44, 2),   # A: white
    ( 0.75, 3),   # F: yellow-white
    ( 1.15, 4),   # G: yellow (Sun-like)
    ( 1.80, 5),   # K: orange
]
_COLOR_IDX_M = 6        # M: red  (bp_rp >= 1.80)
_COLOR_IDX_DEFAULT = 7  # unknown / no colour

# Columns actually present in gaiadr3.gaia_source that we SELECT.
# NOTE: tycho2_source_id is NOT a column in gaiadr3.gaia_source; the
# Tycho-2 cross-match lives in the separate gaiadr3.tycho2tdsc_merge table.
_SELECTED_COLUMNS: frozenset[str] = frozenset(
    {"source_id", "ra", "dec", "phot_g_mean_mag", "bp_rp"}
)


def color_idx_from_bp_rp(bp_rp: float | None) -> int:
    """Map a Gaia Bp-Rp colour index to COLOR_PALETTE position 0–7."""
    if bp_rp is None or math.isnan(bp_rp):
        return _COLOR_IDX_DEFAULT
    for threshold, idx in _BP_RP_THRESHOLDS:
        if bp_rp < threshold:
            return idx
    return _COLOR_IDX_M


def _adql_query(max_mag: float, min_dec: float, min_mag: float) -> str:
    """Build the ADQL SELECT statement.

    All column references must be in *_SELECTED_COLUMNS* — gaiadr3.gaia_source
    does not carry tycho2_source_id; deduplication is done via min_mag.
    """
    return (
        "SELECT source_id, ra, dec, phot_g_mean_mag, bp_rp "  # noqa: S608
        "FROM gaiadr3.gaia_source "
        "WHERE phot_g_mean_mag IS NOT NULL "
        f"AND phot_g_mean_mag > {min_mag} "
        f"AND phot_g_mean_mag < {max_mag} "
        f"AND dec > {min_dec}"
    )


def _get_job_error(job_url: str) -> str:
    """Fetch the error description from a failed TAP job (best-effort)."""
    try:
        with urllib.request.urlopen(f"{job_url}/error", timeout=15) as resp:  # noqa: S310
            return resp.read().decode("utf-8", errors="replace").strip()
    except Exception:
        return "(error details unavailable)"


def _submit_job(query: str, maxrec: int = 20_000_000) -> str:
    """POST an ADQL query to the Gaia async TAP endpoint.

    urllib follows the 303 redirect automatically; returns the final job URL
    (e.g. https://gea.esac.esa.int/tap-server/tap/async/{job_id}).

    *maxrec* overrides the server's default row cap (3 M).  The ESA Gaia async
    TAP accepts values well above 3 M; -1 means unlimited.
    """
    body = urllib.parse.urlencode(
        {
            "REQUEST": "doQuery",
            "LANG": "ADQL",
            "QUERY": query,
            "FORMAT": "csv",
            "PHASE": "RUN",
            "MAXREC": str(maxrec),
        }
    ).encode("ascii")
    req = urllib.request.Request(_GAIA_TAP_ASYNC, data=body, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
        job_url = resp.geturl()
    return job_url.rstrip("/")


def _poll_job(job_url: str) -> None:
    """Block until the TAP job reaches COMPLETED; raise on failure or timeout."""
    phase_url = f"{job_url}/phase"
    deadline = time.monotonic() + _POLL_TIMEOUT_S
    while time.monotonic() < deadline:
        with urllib.request.urlopen(phase_url, timeout=30) as resp:  # noqa: S310
            phase = resp.read().decode("ascii").strip()
        print(f"  [Gaia] job phase: {phase}")
        if phase == "COMPLETED":
            return
        if phase in ("ERROR", "ABORTED", "UNKNOWN"):
            detail = _get_job_error(job_url)
            raise RuntimeError(
                f"Gaia TAP job ended with phase={phase}: {detail}"
            )
        time.sleep(_POLL_INTERVAL_S)
    raise TimeoutError(f"Gaia TAP job timed out after {_POLL_TIMEOUT_S}s")


def _download_result(job_url: str, dest_path: Path) -> None:
    """Stream TAP result CSV to *dest_path* as gzip-compressed bytes."""
    result_url = f"{job_url}/results/result"
    print("  [Gaia] downloading result …")
    with urllib.request.urlopen(result_url, timeout=1800) as resp:  # noqa: S310
        raw = resp.read()
    with gzip.open(dest_path, "wb") as fh:
        fh.write(raw)
    size_mb = dest_path.stat().st_size / 1_048_576
    print(f"  [Gaia] saved {size_mb:.1f} MB (compressed) → {dest_path}")


def fetch_gaia(
    max_mag: float,
    min_dec: float,
    cache_path: Path,
    min_mag: float = 11.5,
) -> Path:
    """Ensure Gaia DR3 supplement is available at *cache_path* and return it.

    Downloads via the async TAP service if the file is absent; otherwise the
    cached file is used as-is.

    *min_mag* should match (or be slightly below) the AT-HYG completeness
    ceiling so that the downloaded stars are additional, not duplicates.
    """
    if cache_path.exists():
        size_mb = cache_path.stat().st_size / 1_048_576
        print(f"  [Gaia] using cached {cache_path.name} ({size_mb:.1f} MB)")
        return cache_path
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    query = _adql_query(max_mag, min_dec, min_mag)
    print(
        f"  [Gaia] submitting async TAP query "
        f"(G {min_mag}–{max_mag}, dec > {min_dec})"
    )
    job_url = _submit_job(query)
    print(f"  [Gaia] job: {job_url}")
    _poll_job(job_url)
    _download_result(job_url, cache_path)
    return cache_path


def load_gaia_stars(
    cache_path: Path,
    max_mag: float,
    min_dec: float,
    color_palette: list[str],
) -> list[dict[str, Any]]:
    """Read the cached Gaia CSV.gz and return a list of minimal star dicts.

    Each entry contains only the fields required by StarPipeline._write_csv:
        pos  — [ra_hours, dec_deg]
        mag  — float (Gaia G-band)
        clr  — hex colour string from *color_palette*
    """
    stars: list[dict[str, Any]] = []
    with gzip.open(cache_path, "rt", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            try:
                mag = float(row["phot_g_mean_mag"])
                ra_deg = float(row["ra"])
                dec = float(row["dec"])
            except (KeyError, ValueError):
                continue
            if mag > max_mag or dec < min_dec:
                continue
            bp_rp_raw = row.get("bp_rp", "")
            try:
                bp_rp: float | None = float(bp_rp_raw) if bp_rp_raw else None
            except ValueError:
                bp_rp = None
            cidx = color_idx_from_bp_rp(bp_rp)
            stars.append(
                {
                    "pos": [ra_deg / 15.0, dec],  # ra in hours for pipeline compat
                    "mag": round(mag, 3),
                    "clr": color_palette[cidx],
                }
            )
    return stars
